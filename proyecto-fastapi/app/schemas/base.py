from datetime import datetime
from pydantic import BaseModel, ConfigDict


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TimestampMixin(APIModel):
    created_at: datetime | None = None
    updated_at: datetime | None = None

    # ESTO SIRVE PARA QUE EL PROYECTO PUEDA LEER OBEJETOS.
