# What the health check says, in plain words

Use these lines to explain each finding of `doctor.py check`. Problems first, then notes, then one line for "everything else is fine".

- Python found (name and version): the helper scripts can run. Not found: the tutor works from text; say what is lost (docs/how-it-works.md).
- Helper scripts off: normal at first. Not a problem. Offer route E only if the learner wants them. Turning them off also stops the safety guard and the secret check; the permission rules in settings.json still apply.
- Helper scripts on but Python missing or wrong name: red "hook error" lines. Offer to turn them off or to fix the name; the learner decides.
- Claude Code older than 2.1.288: the kit was built and checked on 2.1.288. Update the way it was installed; look up the current steps, do not guess them.
- settings.json invalid: Claude Code ignores the whole file, so the safety rules are off. Show the file name and the problem; the learner restores the backup `settings.json.tutor-backup` or the kit's copy.
- Output style does not match: the teacher voice is off. The name in settings.json must be `tutor`.
- Started in a sub-folder: settings are not read there. Close, open the project folder, start again.
- Safety rules missing from settings.json: the permission rules are gone. Same repair as an invalid file.
- `.env` or the notes folder not ignored by Git: a secret or private note could be committed. Fix: the new-project skill adds the missing lines to `.gitignore`, after a yes. New-project writes the first `.gitignore`; later lines are added only after a yes.
- `.gitignore` saved as UTF-16: Git cannot read it. Save it again as UTF-8.
- Git name and e-mail not set: the first save point will ask for them. Not urgent.
- Lesson data damaged: some lessons may be missing. Restore the file from the kit.
- Errors in the helper-script log: names of file and error type only, no text of the learner. One old error is harmless; the same error repeating is worth fixing.
- Kit files changed by the learner: fine if on purpose. An update keeps them and saves the new version as `<file>.new`.
- Teaching numbers out of range: tell it in one plain sentence, without percentages, unless the learner asks (the progress skill has the details).
