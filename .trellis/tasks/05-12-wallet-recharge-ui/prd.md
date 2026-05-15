# PRD: Wallet Recharge UI

## Objective
Add a wallet recharge interface in Settings panel to allow users to add balance.

## Requirements

### 1. Stable Balance Display
- Show current balance prominently in Settings
- Show deduction history/ledger clearly

### 2. Recharge Buttons
- Quick amount buttons: +1, +5, +10, +20, +50 RMB
- Custom amount input field
- Total amount preview before confirming

### 3. Confirmation Dialog
- Show amount to be added
- Confirm/Cancel buttons
- After confirmation, update balance immediately

### 4. Technical Implementation
- Frontend: Add UI in Settings panel
- Backend: Add `/api/billing/recharge` endpoint
- Update wallet balance in memory (no persistent storage needed for local dev)

## UI Layout
```
钱包
余额: ¥X.XXXXXX

充值金额:
[+1] [+5] [+10] [+20] [+50]  [自定义金额: ____]

待充值: ¥X.XX
[充值按钮]

消费记录:
...
```

## Files to Modify
- `web/static/index.html` - Add recharge UI in settings panel
- `web/static/styles.css` - Style recharge buttons and dialog
- `web/static/app.js` - Handle recharge interactions
- `web/ielts_server.py` - Add recharge API endpoint
