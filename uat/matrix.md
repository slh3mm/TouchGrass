# UAT coverage and release matrix

| Area | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| Authentication/global shell | Required | Required | Smoke | Smoke | Required | Required |
| Home | Required | Smoke | Required | — | Smoke | — |
| Passport | Required | Required | Required | — | Smoke | Security |
| Travel Map | Required | Required | Required | — | Smoke | Security |
| Places | Required | Smoke | Required | Smoke | Smoke | Security |
| Trips/planner/photos | Required | Required | Required | Smoke | Smoke | Security |
| Ballparks | Required | Smoke | Required | — | Smoke | — |
| Sharing | Smoke | Required | Required | — | — | Required |
| Settings/integrations | Smoke | Owner controls absent | — | Required | Required | Security |
| Mobile/PWA | Smoke | Required | Smoke | Required | Smoke | — |
| Accessibility/resilience | Smoke | Smoke | Smoke | Smoke | Required | — |

## Release decision

- **Pass:** every critical scenario passes, no P0/P1 remains open, no unresolved security/data-integrity finding exists, and Spencer completes the acceptance checklist.
- **Conditional pass:** no P0/P1 remains and Spencer explicitly accepts each named P2 with its workaround and follow-up owner.
- **Fail:** any P0/P1, critical scenario failure, or unresolved security/data-integrity concern.
- **No decision:** any critical scenario is Blocked or Not run.
