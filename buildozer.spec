[app]
title = Farmer and Costing
package.name = farmercosting
package.domain = org.farmercosting
source.dir = .
source.include_exts = py,kv,json,txt
version = 1.0.0
orientation = portrait
fullscreen = False

# Pin p4a to a release that ships Python 3.11 — Kivy 2.3 + KivyMD master need 3.11
p4a.fork = kivy
p4a.branch = master
p4a.commit = 2024.05.15

requirements = python3==3.11.9,kivy==2.3.0,git+https://github.com/kivymd/KivyMD.git@master,materialyoucolor,asynckivy,asyncgui

android.api = 33
android.minapi = 21
android.accept_sdk_license = True
android.private_storage = True
android.archs = arm64-v8a,armeabi-v7a
android.allow_backup = True

# Signing (needed for the apksigner step to find an existing keystore)
android.keystore = android/debug.keystore
android.keystore.password = android
android.keyalias = androiddebugkey
android.keyalias.password = android

[buildozer]
log_level = 2
warn_on_root = 1
