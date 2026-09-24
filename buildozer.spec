[app]
title = Farmer and Costing
package.name = farmercosting
package.domain = org.farmercosting
source.dir = .
source.include_exts = py,json,txt
version = 1.0.0
orientation = portrait
fullscreen = 0
requirements = python3,kivy,git+https://github.com/kivymd/KivyMD.git@master,materialyoucolor,materialshapes,asynckivy,asyncgui
android.api = 33
android.minapi = 21
android.accept_sdk_license = True
android.private_storage = True
android.archs = arm64-v8a,armeabi-v7a
# Signing (required for consistent debug signing across updates)
android.keystore = android/debug.keystore
android.keystore.password = android
android.keyalias = androiddebugkey
android.keyalias.password = android
[buildozer]
log_level = 2
warn_on_root = 1
