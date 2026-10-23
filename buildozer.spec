[app]

title = SITADELO HISSABI
package.name = hissabi
package.domain = org.sitadelo

source.dir = .
source.include_exts = py,kv,png,jpg,jpeg,atlas,ttf,json,txt
source.exclude_dirs = .git,.github,bin,.buildozer,__pycache__

version = 1.0.0
requirements = python3,kivy

orientation = portrait
fullscreen = 0

android.permissions = INTERNET,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE
android.api = 35
android.minapi = 23
android.archs = arm64-v8a, armeabi-v7a

[buildozer]
log_level = 2
warn_on_root = 1
