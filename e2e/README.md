# E2E Tests — Niv AI

Automated browser tests using [Playwright](https://playwright.dev/).

## Setup

```bash
npm install
npx playwright install chromium
```

## Run Tests

```bash
# Against local Docker
npx playwright test

# Against production
NIV_TEST_URL=https://your-site.example.com NIV_TEST_USER=Administrator NIV_TEST_PASS=yourpass npx playwright test

# Specific test file
npx playwright test e2e/chat.spec.js

# With UI (headed mode)
npx playwright test --headed

# Debug mode
npx playwright test --debug
```

## Test Cases (15 tests)

### Core Chat (6 tests)
1. Page loads with all UI elements
2. Send message and receive AI response
3. Create new conversation
4. Copy button works on AI response
5. Enter key sends message
6. Reactions appear on AI messages

### Features (7 tests)
7. Dark mode toggle
8. Sidebar opens and closes
9. Conversation search filters
10. Tool call renders correctly
11. Export buttons on table responses
12. Voice input button present
13. Widget opens in iframe

### Mobile (2 tests)
14. Mobile layout hides sidebar
15. Mobile input sticky at bottom

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| NIV_TEST_URL | http://localhost:8080 | Frappe site URL |
| NIV_TEST_USER | Administrator | Login username |
| NIV_TEST_PASS | admin | Login password |
