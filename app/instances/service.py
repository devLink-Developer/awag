from sqlalchemy import select

from app.models.entities import Instance


def bootstrap_instance(db, settings):
    instance = db.scalar(select(Instance).where(Instance.adb_serial == settings.adb_serial))
    if instance is None:
        instance = Instance(name=settings.instance_name, adb_serial=settings.adb_serial,
                            appium_url=settings.appium_url, system_port=settings.system_port,
                            phone_number=settings.instance_phone_number)
        db.add(instance)
    else:
        instance.appium_url = settings.appium_url
        instance.system_port = settings.system_port
        instance.name = settings.instance_name
        if settings.instance_phone_number:
            instance.phone_number = settings.instance_phone_number
    db.commit()
    return instance
