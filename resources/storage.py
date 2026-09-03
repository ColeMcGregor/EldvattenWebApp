from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivateResourceStorage(FileSystemStorage):
    def __init__(self, *args, **kwargs):
        kwargs["location"] = (
            settings.PRIVATE_MEDIA_ROOT
        )

        super().__init__(
            *args,
            **kwargs,
        )

    def url(self, name):
        raise NotImplementedError(
            "Private resource files do not have public URLs."
        )


private_resource_storage = (
    PrivateResourceStorage()
)