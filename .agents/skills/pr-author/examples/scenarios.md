# Scenarios

Good: Save the PR template as `workdir/.tmp/pr/fix-timer.md`, then run:

```powershell
gh pr create --draft --base main --title 'Fix timer' --body-file workdir/.tmp/pr/fix-timer.md
gh pr edit 51 --body-file workdir/.tmp/pr/fix-timer.md
gh pr comment 51 --body-file workdir/.tmp/pr/review-51.md
```

Keep these ignored drafts after success. Markdown backticks and line breaks
remain literal because the CLI reads the file.

Bad: Pass multiline Markdown through an interpolated shell string, claim
`tests pass` without evidence, or undraft before the independent ready verdict.

Not a trigger: Review another agent's PR or define a new feature's scope.
