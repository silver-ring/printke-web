import { test, expect } from '@playwright/test';

test.describe('PrintKe Platform E2E Tests', () => {

  test('Admin Dashboard loads correctly', async ({ page }) => {
    // Navigate to Admin Dashboard
    await page.goto('http://localhost:30081');

    // Take screenshot
    await page.screenshot({ path: 'test-results/screenshots/01-admin-dashboard.png', fullPage: true });

    // Check title
    await expect(page).toHaveTitle(/PrintKe Admin/);

    // Check content is visible
    const heading = page.locator('h1');
    await expect(heading).toContainText('PrintKe Admin');

    // Check badges are visible
    await expect(page.getByText('Kubernetes', { exact: true })).toBeVisible();
    await expect(page.getByText('Production Ready', { exact: true })).toBeVisible();

    console.log('✓ Admin Dashboard loaded successfully');
  });

  test('API Health endpoint returns correct response', async ({ page, request }) => {
    // Test API health endpoint
    const response = await request.get('http://localhost:30080/health');

    expect(response.ok()).toBeTruthy();

    const json = await response.json();
    expect(json.status).toBe('healthy');
    expect(json.service).toBe('printke-api');
    expect(json.platform).toBe('kubernetes');

    console.log('✓ API Health check passed:', json);
  });

  test('API Root endpoint works', async ({ request }) => {
    const response = await request.get('http://localhost:30080/');

    expect(response.ok()).toBeTruthy();

    const json = await response.json();
    expect(json.message).toContain('PrintKe API');

    console.log('✓ API Root endpoint works:', json);
  });

  test('MinIO Console loads', async ({ page }) => {
    // Navigate to MinIO Console
    await page.goto('http://localhost:30090');

    // Wait for page to load
    await page.waitForLoadState('networkidle');

    // Take screenshot
    await page.screenshot({ path: 'test-results/screenshots/02-minio-console.png', fullPage: true });

    // Check title contains MinIO
    await expect(page).toHaveTitle(/MinIO/);

    console.log('✓ MinIO Console loaded successfully');
  });

  test('Admin Dashboard links are present', async ({ page }) => {
    await page.goto('http://localhost:30081');

    // Check for API Health link
    const apiHealthLink = page.locator('a[href="/api/health"]');
    await expect(apiHealthLink).toBeVisible();

    // Check for API Docs link
    const apiDocsLink = page.locator('a[href="/api/docs"]');
    await expect(apiDocsLink).toBeVisible();

    console.log('✓ Admin Dashboard links verified');
  });

  test('Take full screenshots of all pages', async ({ page }) => {
    // Admin Dashboard
    await page.goto('http://localhost:30081');
    await page.waitForLoadState('networkidle');
    await page.screenshot({
      path: 'test-results/screenshots/full-admin-dashboard.png',
      fullPage: true
    });

    // MinIO Console
    await page.goto('http://localhost:30090');
    await page.waitForLoadState('networkidle');
    await page.screenshot({
      path: 'test-results/screenshots/full-minio-console.png',
      fullPage: true
    });

    console.log('✓ All screenshots captured');
  });

});
