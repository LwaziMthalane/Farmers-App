[app]

title = Farmer and Costing
package.name = farmercosting
package.domain = org.farmercosting

source.dir = .
source.include_exts = py,kv,json,txt,png,jpg

version = 1.0.0

# NOTE: no version pin on kivy and no separate PyPI "kivymd".
# - kivy: let python-for-android use its own tested recipe (same as the working Vowle build)
# - KivyMD: only the git master build, because main.py uses the KivyMD 2.0 API
#   (MDButtonText, MDTextFieldHintText, MDTopAppBarTitle...)
requirements = python3,kivy,pillow,git+https://github.com/kivymd/KivyMD.git@master,materialyoucolor,asynckivy,asyncgui

orientation = portrait
fullscreen = 0

#
# Android
#
android.api = 33
android.minapi = 21

# NDK intentionally NOT set: let buildozer/p4a pick the NDK they are tested with.
# (The working Vowle build does the same.)
#android.ndk = 27d

android.archs = arm64-v8a, armeabi-v7a
android.private_storage = True
android.allow_backup = True
android.skip_update = False
android.accept_sdk_license = True

# Consistent debug signing for updates (the workflow re-signs with this key)
android.keystore = android/debug.keystore
android.keystore.password = android
android.keyalias = androiddebugkey
android.keyalias.password = android

#
# python-for-android (same as the working build)
#
p4a.fork = kivy
p4a.branch = master
p4a.commit = HEAD


[buildozer]

log_level = 2
warn_on_root = 1
