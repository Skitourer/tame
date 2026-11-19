# Urgency

`tk list` sorts tasks by urgency, highest first, and shows it in the `Urg` column (`tk info`
shows it too). Urgency is a sum of simple terms:

| Term | Value (default weight) |
|---|---|
| Priority | H 6.0, M 3.9, L 1.8 |
| Due date | 12.0 × f, where f grows linearly from 0.2 (due in 14 days or more) to 1.0 (7 days overdue or more) |
| Age | 2.0 × age in years, at most 1 year |
| Tags | 1.0 if the task has any tag |
| Project | 1.0 if the task has a project |

Tasks without a due date get no due term. Urgency is shown with one decimal.

## Example

A task with priority H, due in 7 days, tagged, created today:

- priority H: 6.0
- due in 7 days: f = 0.2 + 0.8 × 7/21 ≈ 0.47, so 12.0 × 0.47 = 5.6
- age: ≈ 0
- tags: 1.0

```text
> tk add Renew passport pri:H due:+7d +admin
> tk
ID   Age   Tags    Pri   Due          Description      Urg
──────────────────────────────────────────────────────────
 1    1s   admin   H     2026-11-26   Renew passport   12.6
```

## Changing the weights

Every weight is a setting (see [Settings](settings.md)):

```sh
tk config set urgency.due 8        # due dates matter less
tk config set urgency.pri_H 10     # priority H matters more
tk config set urgency.tags 0       # ignore tags
tk config unset urgency.due        # back to 12.0
```

Keys: `urgency.pri_H`, `urgency.pri_M`, `urgency.pri_L`, `urgency.due`, `urgency.age`,
`urgency.tags`, `urgency.project`.
