# EDQ Design Tokens

## Colours
- Primary background: #1a1a2e
- Secondary background: #16213e
- Sidebar: #0f1629
- Card: #1e293b
- Accent: #f59e0b
- Accent hover: #d97706
- Success: #10b981
- Danger: #ef4444
- Warning: #f59e0b
- Info: #3b82f6
- Text primary: #ffffff
- Text secondary: #94a3b8
- Text muted: #64748b
- Border: #334155

## Typography
- Headings: Inter, bold
- Body: Inter, regular
- Monospace: JetBrains Mono (IPs, terminal output, technical data)

## Spacing
- xs: 4px, sm: 8px, md: 16px, lg: 24px, xl: 32px

## Border Radius
- sm: 4px, md: 8px, lg: 12px, pill: 9999px
```

**Step 2: Create a designs folder**

In Antigravity's file explorer, right-click your project → New Folder → `designs`

**Step 3: Generate each screen**

Open the Antigravity agent chat and paste this prompt. The agent will read your PRD, understand what each screen needs, and create the .pen design via MCP:

**Login Screen:**
```
Read PRD.md Section 5 (Authentication) and tokens.md for the design system.

Create a new Pencil design file at designs/login.pen

Design a login page for EDQ (Electracom Device Qualifier):
- Full-screen dark background using Primary background from tokens.md
- Centred card (400px wide) with Card background colour and 12px border radius
- "EDQ" text at top in Accent colour, 32px bold
- "Electracom Device Qualifier" subtitle in Text secondary, 14px
- Email input field with dark background and Border colour outline
- Password input field same style
- "Sign In" button full-width, Accent background, white text, 8px radius
- "Electracom Projects Ltd — A Sauter Group Company" at bottom in Text muted, 12px

Use the exact hex colours from tokens.md. No gradients, no shadows.
```

**Dashboard:**
```
Read PRD.md Section 6 (API routes for sessions and devices) and CLAUDE.md 
for the data model. Read tokens.md for colours.

Create a new Pencil design file at designs/dashboard.pen

Design the main dashboard:
- Left sidebar (250px wide, Sidebar background colour):
  Navigation items: Dashboard, New Test, Device Profiles, Templates, Reports, Admin
  Active item has Accent colour left border and Accent text
  Inactive items in Text secondary
  "EDQ" logo at top of sidebar in Accent colour

- Top bar (64px height, Secondary background):
  "Dashboard" title in white
  Right side: notification bell icon, user avatar circle

- Main content area (Primary background):
  Stats row: 4 cards side by side showing:
    "Total Sessions: 47" | "In Progress: 3" | "Completed: 38" | "Failed: 6"
    Each card: Card background, 8px radius, number in white 24px, label in Text secondary
  
  Below stats: "Recent Sessions" heading
  Session cards in a list, each card shows:
    Device name (white, bold) and IP address (monospace, Text secondary)
    Progress bar (Accent fill on dark track)
    Status badge: green pill "Complete", amber pill "In Progress", red pill "Failed"
  
  "New Test Session" button top-right, Accent background

All colours from tokens.md exactly.
```

**Test Session (the main working screen):**
```
Read PRD.md Sections 5 (Three-Tier Test Engine), 9 (Universal Test Library), 
and 26 (Integration Testing Protocol). Read CLAUDE.md for test result data model.
Read tokens.md for colours.

Create a new Pencil design file at designs/test-session.pen

Design the test execution screen:
- Header bar: device name "EasyIO FW08" in white bold, IP "192.168.1.100" in 
  monospace Text secondary, green "Connected" badge pill, category "Controller" badge in Info colour
- Progress bar below header: "18/46 tests complete" with Accent fill

- Two-column layout:
  LEFT (60%): Scrollable test list
    Category headers: "Network Discovery", "TLS/SSL", "SSH Security" etc in Text muted uppercase 12px
    Test cards (Card background, 8px radius, 8px margin between):
      Left: test number "U01" in Text muted, test name in white
      Middle: tool badge pill — "nmap" in blue, "testssl" in purple, "ssh-audit" in green, "hydra" in red
      Right: status icon and small "Run" button
      Status icons: green circle checkmark (Pass), red circle X (Fail), 
        amber triangle (Warning), grey circle (Pending), blue pulsing circle (Running)

  RIGHT (40%): Selected test detail panel (Secondary background)
    Test name at top in white bold
    Terminal output box: dark (#0d1117) background, monospace green text, 300px height, scrollable
    Grade badge: large "PASS" in green or "FAIL" in red
    "Findings" section with bullet points in Text secondary
    "Override Grade" dropdown
    "Add Evidence" button with paperclip icon, outlined style
    "Add Comment" text area

- Bottom action bar:
  "Run All Automated" button (Accent background, white text)
  "Generate Report" button (outlined, white border, white text)

All colours from tokens.md. Monospace font for all IPs and terminal output.
```

**Device Discovery:**
```
Read PRD.md Section 4 (Auto-Discovery & Device Fingerprinting) and Section 7 
(Auto-Discovery Pipeline). Read tokens.md.

Create a new Pencil design file at designs/discovery.pen

Design the new test session / device discovery page:
- Step indicator at top: "Step 1: Discover" (active, Accent), 
  "Step 2: Configure" (inactive, Text muted), "Step 3: Review" (inactive, Text muted)
  Connected by a line, active steps filled, inactive empty circles

- Centre of page:
  Title: "Enter Device IP Address" in white
  Large input field (500px wide) with placeholder "192.168.1.100"
  "Discover" button next to it in Accent colour
  "Scanning..." loading state text below in Text muted (shown during discovery)

- Below input: Device Fingerprint Card (after discovery completes):
  Card background with 8px radius, 500px wide, centred
  Two-column grid inside:
    Manufacturer: "EasyIO" (white bold)
    Model: "FW08" (white)
    MAC Address: "00:1A:2B:3C:4D:5E" (monospace, Text secondary)
    Category: "Controller" (Info colour badge)
    Open Ports row: pills showing "22 SSH", "80 HTTP", "443 HTTPS", "47808 BACnet"
      Each pill: small, rounded, Border background with white text

- Bottom: "Confirm & Start Testing" Accent button
  "Manual Entry" text link in Text secondary below
```

**Manual Test Prompt:**
```
Read PRD.md Section 5 (Three-Tier Test Engine, specifically Tier 2 Guided Manual) 
and Section 9 (test definitions with comment_templates). Read tokens.md.

Create a new Pencil design file at designs/manual-test.pen

Design the manual test guided workflow modal:
- Modal overlay: semi-transparent dark backdrop
- Modal card: 600px wide, Card background, 12px radius
- Header: "Test U12: Physical Security Assessment" in white bold
  Tier badge: "Tier 2 — Guided Manual" in Info colour pill
  
- Instructions box: Secondary background, 8px radius, Border outline
  Instruction text in Text secondary explaining what to check

- Response options (styled as selectable cards, not radio buttons):
  Three cards stacked vertically, 8px gap:
  ○ PASS card: Card background with Success left border (4px)
    "PASS" in Success colour, description in Text secondary
  ○ FAIL card: same style with Danger left border
    "FAIL" in Danger colour, description in Text secondary  
  ○ N/A card: same style with Text muted left border
    "N/A" in Text muted, description in Text secondary
  Selected card: brighter background, thicker left border

- Evidence section: 
  Dashed border drop zone "Drop screenshot or click to upload"
  Small thumbnails of uploaded files

- Comment box: dark textarea with placeholder "Optional notes..."
- Footer: "Submit & Next" Accent button, "Skip" text link in Text muted
```

**Report Generation:**
```
Read PRD.md Section 8 (Reporting & Compliance Engine) and Section 11 
(Template System). Read tokens.md.

Create a new Pencil design file at designs/report.pen

Design the report generation screen:
- Two-panel layout:

  LEFT (40%, Secondary background):
    Title: "Generate Report" in white bold
    Template dropdown: showing "EasyIO Controller Template", "Pelco Camera Template", 
      "Universal Template" as options
    Format selector: "Excel (.xlsx)" selected with radio button, "PDF" unselected
    Checklist "Include Sections":
      ☑ Device Information
      ☑ Test Results Summary
      ☑ Detailed Findings
      ☑ Nessus Vulnerabilities
      ☑ Recommendations
      ☑ Evidence Attachments
    Each checkbox: Accent colour when checked, Border when unchecked
    "Generate Report" Accent button at bottom, full width

  RIGHT (60%, Primary background):
    Preview area with white (#ffffff) background to simulate the Excel output
    Simplified preview showing:
      Electracom logo placeholder at top
      "Device Qualification Report" title
      Table rows: Test Name | Grade | Finding
      Some rows green (Pass), some red (Fail), some amber (Warning)
    "Download" Accent button at bottom-right corner

Colours from tokens.md. The preview area intentionally uses white background 
to contrast with the dark theme — it represents the actual document output.
```

**Step 4: Generate React code from the designs**

Once you're happy with a .pen design, tell the agent:
```
Read designs/login.pen using the Pencil MCP tools.
Read tokens.md for the design system.

Generate a React component from this design.
Use Tailwind CSS classes matching the exact colours and spacing in the design.
Save to frontend/src/pages/Login.jsx.
The login form should POST to /api/auth/login with {email, password}.
Use fetch with credentials: 'include' for cookie-based auth.