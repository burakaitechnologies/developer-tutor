# .gitignore baselines

Read this file when `.gitignore` must be created or repaired (new-project step 8, save-point first save point). Each block below is copy-ready.

## How to use

1. Start with block `general`. Every project gets it. Then add the block of each stack the project uses, below it.
2. Keep the order. A line that starts with `!` lets a file through, so it must come after the line it cancels.
3. Write the file with the Write tool (UTF-8). Never with shell redirection: Windows PowerShell can save UTF-16, and Git cannot read that.
4. Prove it before the first `git add`: `git check-ignore -v .env` must print a line that names `.gitignore`.
5. Lock files (`package-lock.json`, `uv.lock`, `Cargo.lock`) stay in Git. Do not ignore a file only because it is big; ask the learner.
6. A `.gitignore` never removes a file Git already tracks. For a tracked secret see `.claude/rules/safety.md`: revoke first, then `git rm --cached`.

How to read a line: a name that ends in `/` is a folder. A leading `/` means the top folder of the project only. `*` stands for any letters. `#` starts a comment. `!` lets a file through.

## Block: general (every project)

Passwords, keys and local settings. Real values live in `.env`, which Git never saves. `.env.example` (fake values) is let through on purpose.

```gitignore
# Secrets and local settings. Real values live in .env, never in Git.
*.env
.env
.env.*
!.env.example
!.env.sample
!.env.template
!.env.dist
.envrc
*.pem
*.key
*.p12
*.pfx
*.jks
*.keystore
id_rsa*
id_ed25519*
id_ecdsa*
!*.pub
credentials.json
client_secret*.json
service-account*.json

# The tutor's notes about you stay on your computer.
.claude/agent-memory/
.claude/settings.local.json
CLAUDE.local.md

# Files your computer and your editor make by themselves.
.DS_Store
Thumbs.db
desktop.ini
~$*
*~
*.swp
*.swo
.idea/
.vscode/*
!.vscode/extensions.json

# Logs, temporary files and local databases (a database holds real data: back it up elsewhere).
*.log
logs/
tmp/
*.tmp
*.sqlite
*.sqlite3
```

Notes for the tutor: `.env.defaults` and `.env.tpl` are also safe names; add a `!` line if the project uses them. The line `.claude/agent-memory/` keeps the notes out of Git a second time (`.claude/.gitignore` does it too). Do not edit it by hand: the script `doctor.py share-notes on` removes that line, for a private repository only and after the learner agrees. Git cannot let a file through when its folder is ignored.

## Block: node (JavaScript, TypeScript, Node.js)

Libraries that `npm install` downloads again, and build output that the build command makes again.

```gitignore
node_modules/
dist/
build/
.next/
.nuxt/
.svelte-kit/
.turbo/
.parcel-cache/
.cache/
coverage/
*.tsbuildinfo
.eslintcache
npm-debug.log*
yarn-debug.log*
yarn-error.log*
pnpm-debug.log*
.pnpm-store/
.vercel/
.netlify/
```

## Block: python

Compiled caches, virtual environments (a private copy of the libraries), tool caches and local data of web frameworks.

```gitignore
__pycache__/
*.py[cod]
.venv/
venv/
.pytest_cache/
.mypy_cache/
.ruff_cache/
*.egg-info/
dist/
build/
.coverage
htmlcov/
.tox/
instance/
db.sqlite3
staticfiles/
media/
```

## Block: website (plain HTML, CSS and JavaScript)

A plain site builds nothing, so only the folders of site generators are listed. Remove the `#` of a line when you start using that generator. Do not ignore `public/` or `docs/`: many sites keep real files there.

```gitignore
node_modules/
_site/
.jekyll-cache/
.sass-cache/
.hugo_build.lock
# resources/_gen/
```

## Block: data (data analysis and notebooks)

Notebook checkpoints and large binary data files. Add block `python` as well. Clear notebook outputs before a save point: outputs can hold personal data and no ignore line can hide them.

```gitignore
.ipynb_checkpoints/
*.parquet
*.feather
*.h5
*.hdf5
*.pkl
*.pickle
*.npy
*.npz
*.pt
*.pth
*.ckpt
mlruns/
wandb/
# Remove the # when the raw data is big or has personal data:
# data/raw/
# data/private/
# *.csv
```

## Block: game

Engine caches and builds. Browser games use blocks `website` or `node`; Pygame uses block `python`. Keep big pictures and sounds out of Git, and keep their licences in the README.

```gitignore
# Unity
Library/
Temp/
Obj/
Build/
Builds/
Logs/
UserSettings/
MemoryCaptures/
# Godot (export_presets.cfg can hold signing keys)
.godot/
export_presets.cfg
# Packages made for stores
*.apk
*.aab
```

## Block: mobile (Expo, React Native, Flutter, Android, iOS)

Libraries, native build folders and signing files. Add block `node` for Expo and React Native. `google-services.json` and `GoogleService-Info.plist` hold a project key: keep them only if the key is restricted to your app.

```gitignore
.expo/
web-build/
/ios/Pods/
/ios/build/
/android/.gradle/
/android/build/
/android/app/build/
/android/local.properties
key.properties
keystore.properties
.dart_tool/
/build/
.flutter-plugins
.flutter-plugins-dependencies
xcuserdata/
DerivedData/
*.apk
*.aab
*.ipa
*.mobileprovision
*.p8
```

## Block: java and dotnet (Java, Kotlin, C#, .NET)

Compiled output and editor files. Jar files stay in Git because the Gradle wrapper needs one. If you keep your own scripts in a folder named `bin`, remove that line.

```gitignore
# Java and Kotlin
*.class
target/
build/
.gradle/
out/
hs_err_pid*
*.iml
local.properties
# C# and .NET
bin/
obj/
.vs/
*.user
*.suo
*.nupkg
TestResults/
```

## Optional: .gitattributes (Windows line-ending warnings)

If Git prints `LF will be replaced by CRLF` on every command, offer this three-line file with one reason: it makes all text files use the same line endings, so the warning stops and old scripts keep working. Ask for a yes first.

```gitattributes
* text=auto eol=lf
*.bat text eol=crlf
*.cmd text eol=crlf
```
