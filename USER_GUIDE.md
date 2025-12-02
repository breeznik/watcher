# Watcher User Guide

A step-by-step guide to using the Watcher application for monitoring webpages and receiving alerts when specific phrases appear.

## Table of Contents
- [Getting Started](#getting-started)
- [Managing Watchers](#managing-watchers)
- [Understanding Status Types](#understanding-status-types)
- [Manual Checks](#manual-checks)
- [Viewing Logs](#viewing-logs)
- [Email Alerts](#email-alerts)
- [Troubleshooting](#troubleshooting)

---

## Getting Started

### First Login
1. Navigate to your Watcher instance (e.g., `http://localhost` or your deployment URL)
2. Log in with your admin credentials (default: `admin` / `admin123` - **change these in production!**)
3. You'll see the main dashboard with a list of all watchers

### Dashboard Overview
The dashboard displays all your watchers in a table with the following columns:
- **ID** - Unique identifier for each watcher
- **URL** - The webpage being monitored
- **Phrase** - The text being searched for
- **Interval (m)** - How often the page is checked (in minutes)
- **Enabled** - Whether the watcher is currently active
- **Last Status** - Result of the most recent check
- **Last Check** - Timestamp of the last check
- **Actions** - Buttons to manage the watcher

---

## Managing Watchers

### Creating a New Watcher
1. Click the **"+ New Watcher"** button in the top-right
2. Fill in the form:
   - **URL**: The webpage to monitor (e.g., `https://example.com/product`)
   - **Phrase**: The text to search for (case-insensitive, e.g., "In Stock")
   - **Interval**: How often to check, in minutes (minimum: 1)
   - **Emails**: Comma-separated list of recipients for alerts (e.g., `you@example.com, team@example.com`)
   - **Enabled**: Check this box to start monitoring immediately
3. Click **"Create"** to save

### Editing a Watcher
1. Find the watcher in the dashboard
2. Click **"Edit"** in the Actions column
3. Update any fields as needed
4. Click **"Update"** to save changes

### Enabling/Disabling a Watcher
- Click **"Enable"** or **"Disable"** in the Actions column
- Disabled watchers won't run automatic checks but can still be checked manually

### Deleting a Watcher
1. Click **"Delete"** in the Actions column
2. Confirm the deletion in the popup
3. All logs for that watcher will also be removed

---

## Understanding Status Types

After each check, the watcher is assigned one of the following statuses:

- **Found** (green) - The phrase was detected on the page. Email alerts are sent if configured.
- **Not Found** (yellow) - The phrase was not detected on the page.
- **Error** (red) - An error occurred during the check (network issue, invalid URL, etc.)
- **Heavy** (blue) - The page took too long to render (>180 seconds) and was skipped to prevent timeouts.
- **Unknown** (gray) - No check has been performed yet.

---

## Manual Checks

### Running a Manual Check
1. Find the watcher in the dashboard
2. Click **"Check Now"** in the Actions column
3. You'll be redirected to the logs page with a notice that the check has started
4. Refresh the page after a moment to see the results

### Important Notes
- Manual checks run in the background and may take up to **180 seconds** for heavy pages
- **Performance depends on your hosting environment** - rendering times will vary based on available CPU, memory, and network bandwidth
- Only **one manual check per watcher** can run at a time
- If you click "Check Now" while a check is already running, you'll see an alert asking you to wait
- Manual checks won't trigger the nginx timeout page because they're processed asynchronously

---

## Viewing Logs

### Accessing Logs
1. Click **"Logs"** in the Actions column for any watcher
2. You'll see the last 50 checks with:
   - **Checked At** - Timestamp (UTC)
   - **Status** - Result of the check
   - **Error** - Details if the check failed

### Interpreting Logs
- Look for patterns in failed checks to diagnose issues
- If you see repeated "Heavy" statuses, the page may require optimization or a different monitoring approach
- Successful "Found" checks indicate alerts were sent (if emails are configured)

---

## Email Alerts

### Configuring Email Alerts
1. Ensure SMTP settings are configured in your environment (`.env` file):
   ```
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=your-email@gmail.com
   SMTP_PASSWORD=your-app-password
   SMTP_TLS=true
   FROM_EMAIL=your-email@gmail.com
   ```
2. Add recipient email addresses to each watcher (comma-separated)

### When Alerts Are Sent
- Emails are **only sent when the phrase is found** (status: "Found")
- Each alert includes:
  - Watcher ID
  - URL being monitored
  - Phrase that was found
  - Timestamp of detection

### Troubleshooting Email Issues
- Check the application logs for SMTP errors
- Verify SMTP credentials and host/port settings
- Some providers (like Gmail) require app-specific passwords
- Ensure `FROM_EMAIL` matches your SMTP user

---

## Troubleshooting

### Watcher Shows "Error" Status
**Possible causes:**
- Invalid or unreachable URL
- Network connectivity issues
- Blocked by firewall or anti-bot measures
- Page requires authentication

**Solutions:**
- Verify the URL is correct and accessible
- Check application logs for detailed error messages
- Try the URL in a regular browser

### Watcher Shows "Heavy" Status
**Cause:** The page took more than 180 seconds to load/render

**Solutions:**
- The page may be too complex or slow for your hosting environment
- Consider upgrading system resources (CPU, RAM) if this happens frequently
- Monitor a lighter endpoint or use a different approach
- Check if the site has API endpoints you can monitor instead
- Note: Rendering performance varies by system - what works on one server may timeout on another

### Phrase Not Being Detected (Shows "Not Found")
**Common issues:**
- Phrase is misspelled or case doesn't match
- Phrase appears only after JavaScript execution:
  - Ensure `RENDER_JS=true` in your environment
  - Increase `RENDER_POST_WAIT_SECONDS` to allow more time for dynamic content
- Phrase is inside an iframe or loaded via AJAX after page load

**Solutions:**
- Use your browser's "View Source" to confirm the phrase appears in HTML
- Try a more unique phrase that's less likely to change
- Use browser DevTools to inspect when/how the phrase loads

### Manual Check Doesn't Show Results
**Cause:** Check is still running in the background

**Solution:**
- Wait 30-180 seconds depending on page complexity and your hosting environment
- Performance varies based on system resources (CPU, memory, network speed)
- Refresh the logs page to see updated results
- If no result appears after 3 minutes, check application logs

### Can't Click "Check Now" Again
**Cause:** A manual check is already in progress

**Solution:**
- Wait for the current check to complete (up to 180 seconds)
- Refresh the logs page to verify completion
- Only one manual check per watcher can run at a time

---

## Advanced Configuration

### JavaScript Rendering Settings
If monitoring pages with dynamic content loaded via JavaScript:

1. Enable JS rendering: `RENDER_JS=true`
2. Adjust timeout: `RENDER_TIMEOUT=60` (default: 20, max: 180 seconds)
   - **Note:** Actual processing time depends on your hosting system's resources
   - Lower-spec systems may need more conservative timeout values
3. Add post-render wait: `RENDER_POST_WAIT_SECONDS=5` (default: 3)
4. Optional CSS selector wait: `DEBUG_WAIT_SELECTOR=.product-price`

**Performance Considerations:**
- JS rendering with Playwright is resource-intensive
- Systems with limited CPU/RAM may experience slower rendering
- Test with different timeout values to find what works for your environment

### Debug Mode
To save screenshots and HTML snapshots for troubleshooting:

```
DEBUG_DUMP_ARTIFACTS=true
DEBUG_ARTIFACTS_DIR=./data/artifacts
```

Artifacts will be saved to `data/artifacts/watcher_{id}/` with timestamps.

### Timezone Configuration
Set your preferred timezone for scheduled checks:

```
TIMEZONE=America/New_York
```

All logs are stored in UTC but you can adjust the scheduler timezone.

---

## Best Practices

1. **Start with longer intervals** (5-10 minutes) to avoid overwhelming target sites
2. **Use specific phrases** that are unique and unlikely to change
3. **Enable JS rendering only when needed** - it's slower and uses more resources
4. **Monitor email deliverability** - check spam folders and verify SMTP configuration
5. **Keep your admin password secure** - change it from the default immediately
6. **Review logs regularly** to ensure watchers are functioning correctly
7. **Use manual checks sparingly** - they're meant for testing, not regular monitoring

---

## Support & Contributing

- Found a bug? Check application logs first
- Need help? Review the main [README.md](README.md) for technical details
- Want to contribute? See the repository for development setup

---

**Happy Watching! 🔍**
