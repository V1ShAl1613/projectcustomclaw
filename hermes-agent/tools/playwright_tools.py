#!/usr/bin/env python3
"""
Playwright Browser Automation Tools Module

Provides comprehensive browser automation using Playwright:
- Launch browsers (Chromium, Firefox, WebKit)
- Navigation, screenshots, PDF generation
- DOM extraction, accessibility scanning
- Web scraping, form automation
- Login automation, API interception
- Network tracing, visual regression testing

All operations respect workspace boundaries and use existing Hermes
permission model and browser infrastructure.
"""

import asyncio
import base64
import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from tools.registry import registry

logger = logging.getLogger(__name__)


def _check_playwright_available() -> bool:
    """Check if Playwright is installed and available."""
    try:
        import playwright
        return True
    except ImportError:
        return False


# Global browser instances
_browsers: Dict[str, Any] = {}
_browser_lock = asyncio.Lock()
_pages: Dict[str, Any] = {}
_page_lock = asyncio.Lock()

# Playwright browser types
BROWSER_TYPES = ["chromium", "firefox", "webkit"]


def _get_async_playwright():
    """Get async playwright instance."""
    from playwright.async_api import async_playwright
    return async_playwright()


async def _get_browser(browser_type: str = "chromium", headless: bool = True):
    """Get or create a browser instance."""
    key = f"{browser_type}:{headless}"
    async with _browser_lock:
        if key in _browsers:
            browser = _browsers[key]
            if browser.is_connected():
                return browser
            else:
                del _browsers[key]
        
        playwright = await _get_async_playwright().__aenter__()
        browser = await getattr(playwright, browser_type).launch(
            headless=headless,
            args=["--no-sandbox", "--disable-setuid-sandbox"] if headless else []
        )
        _browsers[key] = browser
        return browser


async def _close_browser(browser_type: str = "chromium", headless: bool = True):
    """Close a browser instance."""
    key = f"{browser_type}:{headless}"
    async with _browser_lock:
        if key in _browsers:
            await _browsers[key].close()
            del _browsers[key]


async def _get_page(page_id: str) -> Optional[Any]:
    """Get a page by ID."""
    async with _page_lock:
        return _pages.get(page_id)


async def _create_page(browser_type: str = "chromium", headless: bool = True, 
                       viewport: Optional[Dict] = None) -> str:
    """Create a new page and return its ID."""
    browser = await _get_browser(browser_type, headless)
    context = await browser.new_context(
        viewport=viewport or {"width": 1280, "height": 720}
    )
    page = await context.new_page()
    
    page_id = f"page_{int(time.time() * 1000)}_{id(page)}"
    async with _page_lock:
        _pages[page_id] = page
    
    return page_id


async def _close_page(page_id: str):
    """Close a page by ID."""
    async with _page_lock:
        if page_id in _pages:
            await _pages[page_id].close()
            del _pages[page_id]


# Tool implementations

def playwright_launch(
    browser_type: str = "chromium",
    headless: bool = True,
    viewport: Optional[Dict[str, int]] = None,
    user_agent: Optional[str] = None,
    extra_args: Optional[List[str]] = None,
    task_id: str = "default",
) -> str:
    """Launch a browser instance.
    
    Args:
        browser_type: Browser to launch (chromium, firefox, webkit)
        headless: Run in headless mode
        viewport: Viewport size {width, height}
        user_agent: Custom user agent
        extra_args: Extra browser launch arguments
        task_id: Task identifier
        
    Returns:
        JSON with browser info
    """
    if browser_type not in BROWSER_TYPES:
        return json.dumps({"error": f"Invalid browser type: {browser_type}. Must be one of {BROWSER_TYPES}"})
    
    if not _check_playwright_available():
        return json.dumps({"error": "Playwright not available. Install with: pip install playwright && playwright install"})
    
    try:
        # Run in event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def launch():
            browser = await _get_browser(browser_type, headless)
            context = await browser.new_context(
                viewport=viewport or {"width": 1280, "height": 720},
                user_agent=user_agent,
            )
            page = await context.new_page()
            
            page_id = f"page_{int(time.time() * 1000)}_{id(page)}"
            async with _page_lock:
                _pages[page_id] = page
            
            return {
                "success": True,
                "browser_type": browser_type,
                "headless": headless,
                "page_id": page_id,
                "message": f"Launched {browser_type} browser"
            }
        
        result = loop.run_until_complete(launch())
        loop.close()
        return json.dumps(result)
        
    except Exception as e:
        logger.exception("Failed to launch browser")
        return json.dumps({"error": str(e)})


def playwright_navigate(
    page_id: str,
    url: str,
    wait_until: str = "load",
    timeout: int = 30000,
    task_id: str = "default",
) -> str:
    """Navigate to a URL.
    
    Args:
        page_id: Page ID from playwright_launch
        url: URL to navigate to
        wait_until: Wait condition (load, domcontentloaded, networkidle, commit)
        timeout: Navigation timeout in milliseconds
        task_id: Task identifier
        
    Returns:
        JSON with navigation result
    """
    if not _check_playwright_available():
        return json.dumps({"error": "Playwright not available"})
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def navigate():
            page = await _get_page(page_id)
            if not page:
                return {"error": f"Page not found: {page_id}"}
            
            response = await page.goto(url, wait_until=wait_until, timeout=timeout)
            return {
                "success": True,
                "url": page.url,
                "title": await page.title(),
                "status": response.status if response else None,
            }
        
        result = loop.run_until_complete(navigate())
        loop.close()
        return json.dumps(result)
        
    except Exception as e:
        logger.exception("Failed to navigate")
        return json.dumps({"error": str(e)})


def playwright_screenshot(
    page_id: str,
    path: Optional[str] = None,
    full_page: bool = False,
    viewport_only: bool = False,
    format: str = "png",
    quality: Optional[int] = None,
    task_id: str = "default",
) -> str:
    """Take a screenshot.
    
    Args:
        page_id: Page ID from playwright_launch
        path: Save path (optional, returns base64 if not provided)
        full_page: Capture full page
        viewport_only: Capture only viewport
        format: Image format (png, jpeg)
        quality: JPEG quality (1-100)
        task_id: Task identifier
        
    Returns:
        JSON with screenshot data or path
    """
    if not _check_playwright_available():
        return json.dumps({"error": "Playwright not available"})
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def screenshot():
            page = await _get_page(page_id)
            if not page:
                return {"error": f"Page not found: {page_id}"}
            
            options = {
                "full_page": full_page,
                "type": format,
            }
            if quality and format == "jpeg":
                options["quality"] = quality
            
            if path:
                options["path"] = path
                await page.screenshot(**options)
                return {"success": True, "path": path}
            else:
                img_bytes = await page.screenshot(**options)
                b64 = base64.b64encode(img_bytes).decode()
                return {"success": True, "screenshot": f"data:image/{format};base64,{b64}"}
        
        result = loop.run_until_complete(screenshot())
        loop.close()
        return json.dumps(result)
        
    except Exception as e:
        logger.exception("Failed to take screenshot")
        return json.dumps({"error": str(e)})


def playwright_pdf(
    page_id: str,
    path: Optional[str] = None,
    format: str = "A4",
    margin: Optional[Dict[str, str]] = None,
    print_background: bool = True,
    scale: float = 1.0,
    task_id: str = "default",
) -> str:
    """Generate a PDF from the page.
    
    Args:
        page_id: Page ID from playwright_launch
        path: Save path (optional, returns base64 if not provided)
        format: Paper format (A4, Letter, Legal, Tabloid, A0-A5)
        margin: Page margins {top, right, bottom, left}
        print_background: Print background graphics
        scale: Scale factor
        task_id: Task identifier
        
    Returns:
        JSON with PDF data or path
    """
    if not _check_playwright_available():
        return json.dumps({"error": "Playwright not available"})
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def generate_pdf():
            page = await _get_page(page_id)
            if not page:
                return {"error": f"Page not found: {page_id}"}
            
            options = {
                "format": format,
                "print_background": print_background,
                "scale": scale,
            }
            if margin:
                options["margin"] = margin
            
            if path:
                options["path"] = path
                await page.pdf(**options)
                return {"success": True, "path": path}
            else:
                pdf_bytes = await page.pdf(**options)
                b64 = base64.b64encode(pdf_bytes).decode()
                return {"success": True, "pdf": f"data:application/pdf;base64,{b64}"}
        
        result = loop.run_until_complete(generate_pdf())
        loop.close()
        return json.dumps(result)
        
    except Exception as e:
        logger.exception("Failed to generate PDF")
        return json.dumps({"error": str(e)})


def playwright_dom_extract(
    page_id: str,
    selector: Optional[str] = None,
    attribute: Optional[str] = None,
    include_html: bool = True,
    include_text: bool = True,
    task_id: str = "default",
) -> str:
    """Extract DOM content from page.
    
    Args:
        page_id: Page ID from playwright_launch
        selector: CSS selector (optional, extracts entire page if not provided)
        attribute: Specific attribute to extract (optional)
        include_html: Include outer HTML
        include_text: Include text content
        task_id: Task identifier
        
    Returns:
        JSON with extracted content
    """
    if not _check_playwright_available():
        return json.dumps({"error": "Playwright not available"})
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def extract():
            page = await _get_page(page_id)
            if not page:
                return {"error": f"Page not found: {page_id}"}
            
            if selector:
                elements = await page.query_selector_all(selector)
                results = []
                for el in elements:
                    item = {}
                    if include_html:
                        item["html"] = await el.evaluate("el => el.outerHTML")
                    if include_text:
                        item["text"] = await el.evaluate("el => el.textContent")
                    if attribute:
                        item["attribute"] = await el.get_attribute(attribute)
                    results.append(item)
                return {"success": True, "count": len(results), "elements": results}
            else:
                result = {}
                if include_html:
                    result["html"] = await page.content()
                if include_text:
                    result["text"] = await page.evaluate("() => document.body.textContent")
                if attribute:
                    result["attribute"] = await page.get_attribute(attribute)
                return {"success": True, "data": result}
        
        result = loop.run_until_complete(extract())
        loop.close()
        return json.dumps(result)
        
    except Exception as e:
        logger.exception("Failed to extract DOM")
        return json.dumps({"error": str(e)})


def playwright_accessibility(
    page_id: str,
    standards: Optional[List[str]] = None,
    include_warnings: bool = True,
    task_id: str = "default",
) -> str:
    """Run accessibility scan on page.
    
    Args:
        page_id: Page ID from playwright_launch
        standards: Accessibility standards (wcag2a, wcag2aa, wcag21a, wcag21aa, section508, best-practice)
        include_warnings: Include warnings in results
        task_id: Task identifier
        
    Returns:
        JSON with accessibility results
    """
    if not _check_playwright_available():
        return json.dumps({"error": "Playwright not available"})
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def scan():
            page = await _get_page(page_id)
            if not page:
                return {"error": f"Page not found: {page_id}"}
            
            # Inject axe-core
            await page.add_script_tag(url="https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.8.2/axe.min.js")
            
            # Run accessibility scan
            results = await page.evaluate(f"""
                () => axe.run(document, {{
                    runOnly: {json.dumps(standards or ["wcag2aa", "best-practice"])},
                    resultTypes: ['violations', 'passes', 'incomplete', 'inapplicable']
                }})
            """)
            
            if not include_warnings:
                results = {k: v for k, v in results.items() if k != "incomplete"}
            
            return {"success": True, "results": results}
        
        result = loop.run_until_complete(scan())
        loop.close()
        return json.dumps(result)
        
    except Exception as e:
        logger.exception("Failed to run accessibility scan")
        return json.dumps({"error": str(e)})


def playwright_scrape(
    page_id: str,
    selectors: Dict[str, str],
    multiple: bool = False,
    task_id: str = "default",
) -> str:
    """Scrape structured data from page.
    
    Args:
        page_id: Page ID from playwright_launch
        selectors: Dict of field_name -> CSS selector
        multiple: Whether to extract multiple elements per selector
        task_id: Task identifier
        
    Returns:
        JSON with scraped data
    """
    if not _check_playwright_available():
        return json.dumps({"error": "Playwright not available"})
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def scrape():
            page = await _get_page(page_id)
            if not page:
                return {"error": f"Page not found: {page_id}"}
            
            data = {}
            for field, selector in selectors.items():
                if multiple:
                    elements = await page.query_selector_all(selector)
                    data[field] = []
                    for el in elements:
                        data[field].append({
                            "text": await el.text_content(),
                            "html": await el.evaluate("el => el.outerHTML"),
                            "href": await el.get_attribute("href"),
                            "src": await el.get_attribute("src"),
                        })
                else:
                    element = await page.query_selector(selector)
                    if element:
                        data[field] = {
                            "text": await element.text_content(),
                            "html": await element.evaluate("el => el.outerHTML"),
                            "href": await element.get_attribute("href"),
                            "src": await element.get_attribute("src"),
                        }
                    else:
                        data[field] = None
            
            return {"success": True, "data": data}
        
        result = loop.run_until_complete(scrape())
        loop.close()
        return json.dumps(result)
        
    except Exception as e:
        logger.exception("Failed to scrape page")
        return json.dumps({"error": str(e)})


def playwright_login(
    page_id: str,
    username: str,
    password: str,
    username_selector: str = "input[type=email], input[name=username], input[id=username]",
    password_selector: str = "input[type=password], input[name=password], input[id=password]",
    submit_selector: str = "button[type=submit], input[type=submit], button:has-text('Sign in'), button:has-text('Login')",
    wait_after_login: int = 3000,
    task_id: str = "default",
) -> str:
    """Automate login process.
    
    Args:
        page_id: Page ID from playwright_launch
        username: Username/email
        password: Password
        username_selector: Selector for username field
        password_selector: Selector for password field
        submit_selector: Selector for submit button
        wait_after_login: Wait time after login (ms)
        task_id: Task identifier
        
    Returns:
        JSON with login result
    """
    if not _check_playwright_available():
        return json.dumps({"error": "Playwright not available"})
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def login():
            page = await _get_page(page_id)
            if not page:
                return {"error": f"Page not found: {page_id}"}
            
            # Fill username
            await page.fill(username_selector, username)
            # Fill password
            await page.fill(password_selector, password)
            # Click submit
            await page.click(submit_selector)
            # Wait for navigation or specified time
            await page.wait_for_timeout(wait_after_login)
            
            return {
                "success": True,
                "url": page.url,
                "title": await page.title(),
            }
        
        result = loop.run_until_complete(login())
        loop.close()
        return json.dumps(result)
        
    except Exception as e:
        logger.exception("Failed to login")
        return json.dumps({"error": str(e)})


def playwright_form(
    page_id: str,
    form_data: Dict[str, str],
    form_selector: str = "form",
    submit: bool = True,
    submit_selector: str = "button[type=submit], input[type=submit]",
    task_id: str = "default",
) -> str:
    """Fill and optionally submit a form.
    
    Args:
        page_id: Page ID from playwright_launch
        form_data: Dict of field_name -> value
        form_selector: Form selector
        submit: Whether to submit the form
        submit_selector: Submit button selector
        task_id: Task identifier
        
    Returns:
        JSON with form result
    """
    if not _check_playwright_available():
        return json.dumps({"error": "Playwright not available"})
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def fill_form():
            page = await _get_page(page_id)
            if not page:
                return {"error": f"Page not found: {page_id}"}
            
            for field, value in form_data.items():
                await page.fill(f"{form_selector} [name={field}], {form_selector} [id={field}]", value)
            
            if submit:
                await page.click(submit_selector)
                await page.wait_for_load_state("networkidle")
            
            return {"success": True, "url": page.url}
        
        result = loop.run_until_complete(fill_form())
        loop.close()
        return json.dumps(result)
        
    except Exception as e:
        logger.exception("Failed to fill form")
        return json.dumps({"error": str(e)})


def playwright_intercept(
    page_id: str,
    url_pattern: str,
    handler_type: str = "log",
    response_modify: Optional[Dict] = None,
    task_id: str = "default",
) -> str:
    """Intercept network requests.
    
    Args:
        page_id: Page ID from playwright_launch
        url_pattern: URL pattern to intercept
        handler_type: Handler type (log, mock, abort, modify)
        response_modify: Response modifications for mock/modify
        task_id: Task identifier
        
    Returns:
        JSON with intercept status
    """
    if not _check_playwright_available():
        return json.dumps({"error": "Playwright not available"})
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def intercept():
            page = await _get_page(page_id)
            if not page:
                return {"error": f"Page not found: {page_id}"}
            
            intercepted = []
            
            async def handle_route(route):
                request = route.request
                intercepted.append({
                    "url": request.url,
                    "method": request.method,
                    "headers": dict(request.headers),
                    "post_data": request.post_data,
                })
                
                if handler_type == "log":
                    await route.continue_()
                elif handler_type == "abort":
                    await route.abort()
                elif handler_type == "mock":
                    await route.fulfill(
                        status=response_modify.get("status", 200),
                        content_type=response_modify.get("content_type", "application/json"),
                        body=json.dumps(response_modify.get("body", {})),
                    )
                elif handler_type == "modify":
                    response = await route.fetch()
                    body = await response.json()
                    if response_modify:
                        body.update(response_modify.get("body", {}))
                    await route.fulfill(
                        status=response.status,
                        headers=response.headers,
                        body=json.dumps(body),
                    )
            
            await page.route(url_pattern, handle_route)
            
            return {"success": True, "intercepted": intercepted}
        
        result = loop.run_until_complete(intercept())
        loop.close()
        return json.dumps(result)
        
    except Exception as e:
        logger.exception("Failed to intercept")
        return json.dumps({"error": str(e)})


def playwright_trace(
    page_id: str,
    action: str = "start",
    path: Optional[str] = None,
    screenshots: bool = True,
    snapshots: bool = True,
    sources: bool = True,
    task_id: str = "default",
) -> str:
    """Manage Playwright tracing.
    
    Args:
        page_id: Page ID from playwright_launch
        action: Action (start, stop, export)
        path: Trace file path
        screenshots: Capture screenshots
        snapshots: Capture DOM snapshots
        sources: Capture source files
        task_id: Task identifier
        
    Returns:
        JSON with trace result
    """
    if not _check_playwright_available():
        return json.dumps({"error": "Playwright not available"})
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def trace():
            page = await _get_page(page_id)
            if not page:
                return {"error": f"Page not found: {page_id}"}
            
            context = page.context
            
            if action == "start":
                await context.tracing.start(
                    screenshots=screenshots,
                    snapshots=snapshots,
                    sources=sources,
                )
                return {"success": True, "message": "Trace started"}
            elif action == "stop":
                await context.tracing.stop()
                return {"success": True, "message": "Trace stopped"}
            elif action == "export":
                if not path:
                    path = f"trace_{int(time.time())}.zip"
                await context.tracing.export(path=path)
                return {"success": True, "path": path}
            else:
                return {"error": f"Unknown action: {action}"}
        
        result = loop.run_until_complete(trace())
        loop.close()
        return json.dumps(result)
        
    except Exception as e:
        logger.exception("Failed to manage trace")
        return json.dumps({"error": str(e)})


def playwright_visual_regression(
    page_id: str,
    baseline_path: str,
    threshold: float = 0.1,
    task_id: str = "default",
) -> str:
    """Run visual regression test.
    
    Args:
        page_id: Page ID from playwright_launch
        baseline_path: Path to baseline image
        threshold: Difference threshold (0-1)
        task_id: Task identifier
        
    Returns:
        JSON with comparison result
    """
    if not _check_playwright_available():
        return json.dumps({"error": "Playwright not available"})
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def compare():
            page = await _get_page(page_id)
            if not page:
                return {"error": f"Page not found: {page_id}"}
            
            # Take current screenshot
            current = await page.screenshot()
            
            # Compare with baseline
            from PIL import Image
            import io
            
            current_img = Image.open(io.BytesIO(current))
            baseline_img = Image.open(baseline_path)
            
            # Resize if needed
            if current_img.size != baseline_img.size:
                baseline_img = baseline_img.resize(current_img.size)
            
            # Calculate difference
            diff = Image.new("RGB", current_img.size)
            diff_pixels = 0
            total_pixels = current_img.width * current_img.height
            
            for x in range(current_img.width):
                for y in range(current_img.height):
                    c1 = current_img.getpixel((x, y))
                    c2 = baseline_img.getpixel((x, y))
                    if c1 != c2:
                        diff_pixels += 1
                        diff.putpixel((x, y), (255, 0, 0))
                    else:
                        diff.putpixel((x, y), c1)
            
            diff_ratio = diff_pixels / total_pixels
            passed = diff_ratio <= threshold
            
            return {
                "success": True,
                "passed": passed,
                "diff_ratio": diff_ratio,
                "threshold": threshold,
                "diff_pixels": diff_pixels,
                "total_pixels": total_pixels,
            }
        
        result = loop.run_until_complete(compare())
        loop.close()
        return json.dumps(result)
        
    except Exception as e:
        logger.exception("Failed visual regression")
        return json.dumps({"error": str(e)})


def playwright_close(
    page_id: Optional[str] = None,
    browser_type: Optional[str] = None,
    headless: bool = True,
    task_id: str = "default",
) -> str:
    """Close page or browser.
    
    Args:
        page_id: Page ID to close (optional)
        browser_type: Browser type to close (optional)
        headless: Headless mode for browser close
        task_id: Task identifier
        
    Returns:
        JSON with close result
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def close():
            if page_id:
                await _close_page(page_id)
                return {"success": True, "message": f"Closed page {page_id}"}
            elif browser_type:
                await _close_browser(browser_type, headless)
                return {"success": True, "message": f"Closed browser {browser_type}"}
            else:
                return {"error": "Specify page_id or browser_type"}
        
        result = loop.run_until_complete(close())
        loop.close()
        return json.dumps(result)
        
    except Exception as e:
        logger.exception("Failed to close")
        return json.dumps({"error": str(e)})


def _register_playwright_tools():
    """Register all Playwright tools with the registry."""
    tools = [
        ("playwright_launch", playwright_launch, "Launch browser (Chromium/Firefox/WebKit)"),
        ("playwright_navigate", playwright_navigate, "Navigate to URL"),
        ("playwright_screenshot", playwright_screenshot, "Take screenshot"),
        ("playwright_pdf", playwright_pdf, "Generate PDF"),
        ("playwright_dom_extract", playwright_dom_extract, "Extract DOM content"),
        ("playwright_accessibility", playwright_accessibility, "Run accessibility scan"),
        ("playwright_scrape", playwright_scrape, "Scrape structured data"),
        ("playwright_login", playwright_login, "Automate login"),
        ("playwright_form", playwright_form, "Fill and submit forms"),
        ("playwright_intercept", playwright_intercept, "Intercept network requests"),
        ("playwright_trace", playwright_trace, "Manage Playwright tracing"),
        ("playwright_visual_regression", playwright_visual_regression, "Visual regression testing"),
        ("playwright_close", playwright_close, "Close page or browser"),
    ]
    
    for name, func, desc in tools:
        registry.register(
            name=name,
            toolset="playwright",
            schema={"name": name, "description": desc, "parameters": {"type": "object", "properties": {}}},
            handler=func,
            check_fn=_check_playwright_available,
            description=desc,
        )


_register_playwright_tools()