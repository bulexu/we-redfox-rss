import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from driver.playwright_driver import PlaywrightController


class PlaywrightLaunchTests(unittest.IsolatedAsyncioTestCase):
    async def start_controller(self, browser_type, **options):
        page = AsyncMock()
        context = AsyncMock()
        context.new_page.return_value = page
        browser = AsyncMock()
        browser.new_context.return_value = context
        launcher = SimpleNamespace(launch=AsyncMock(return_value=browser))
        playwright = SimpleNamespace(**{browser_type: launcher})
        manager = SimpleNamespace(start=AsyncMock(return_value=playwright))
        controller = PlaywrightController(browser_type=browser_type, **options)

        with patch("playwright.async_api.async_playwright", return_value=manager):
            await controller.start_browser()

        self.assertIs(controller._page, page)
        page.add_init_script.assert_awaited_once()
        return launcher.launch.call_args.kwargs

    async def test_webkit_and_firefox_start_without_chromium_arguments(self):
        for browser_type in ("webkit", "firefox"):
            with self.subTest(browser_type=browser_type):
                options = await self.start_controller(
                    browser_type, headless=True, proxy_url="http://127.0.0.1:8080"
                )
                self.assertNotIn("args", options)
                self.assertTrue(options["headless"])
                self.assertEqual(options["proxy"], {"server": "http://127.0.0.1:8080"})

    async def test_chromium_keeps_container_and_anti_detection_arguments(self):
        options = await self.start_controller("chromium", headless=False)
        self.assertEqual(options["args"], [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-setuid-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-gpu",
            "--disable-software-rasterizer",
        ])
        self.assertFalse(options["headless"])
        self.assertNotIn("proxy", options)


if __name__ == "__main__":
    unittest.main()
