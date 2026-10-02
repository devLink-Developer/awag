from app.config.settings import get_settings
from app.instances.service import bootstrap_instance
from app.services.database import session_factory

with session_factory()() as db:
    instance = bootstrap_instance(db, get_settings())
    print(instance.id)
