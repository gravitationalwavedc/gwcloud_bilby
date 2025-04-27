# End-to-End Testing with React Frontend

This directory contains end-to-end tests for the GWCloud Bilby application, including tests for the React frontend.

## Overview

The tests use [Playwright](https://playwright.dev/) through the `adacs-django-playwright` package, which integrates Playwright with Django's test framework. We've extended this to also test the React frontend by:

1. Building the React app before tests run
2. Starting a Vite preview server to serve the built files
3. Using Playwright to interact with both the Django backend and React frontend

## Test Classes

### `PlaywrightTestCase`

The base test case class from `adacs-django-playwright` that sets up Playwright and a Django test server.

### `ReactPlaywrightTestCase`

An extended test case class that adds support for testing the React frontend. It:

- Ensures the React app is built (only once for the entire test suite)
- Ensures a Vite preview server is running (reused between test classes)
- Provides helper methods for interacting with the React frontend
- Automatically cleans up the server when all tests are complete

## Writing Tests

### Testing the Django Backend

Use the `PlaywrightTestCase` class for tests that only need to interact with the Django backend:

```python
from adacs_django_playwright.adacs_django_playwright import PlaywrightTestCase
from playwright.sync_api import expect

class TestBackend(PlaywrightTestCase):
    def test_graphql_endpoint(self):
        page = self.browser.new_page()
        try:
            page.goto(f"{self.live_server_url}/graphql")
            expect(page.locator(".graphiql")).to_be_visible()
        finally:
            page.close()
```

### Testing the React Frontend

Use the `ReactPlaywrightTestCase` class for tests that need to interact with the React frontend:

```python
from playwright.sync_api import expect
from .react_test_case import ReactPlaywrightTestCase

class TestFrontend(ReactPlaywrightTestCase):
    def test_homepage(self):
        page = self.browser.new_page()
        try:
            page.goto(self.react_url)
            expect(page).to_have_title("GWCloud Bilby")
            expect(page.locator("nav")).to_be_visible()
        finally:
            page.close()
```

## Running Tests

Run the tests using Django's test command:

```bash
cd src
python development-manage.py test e2e_tests
```
