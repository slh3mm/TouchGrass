from django.contrib import admin

from .models import PhotoAsset, PhotoImportSource, PhotoMatchSuggestion, PhotoScanRun, TripPhotoLink

admin.site.register(PhotoImportSource)
admin.site.register(PhotoAsset)
admin.site.register(TripPhotoLink)
admin.site.register(PhotoMatchSuggestion)
admin.site.register(PhotoScanRun)
