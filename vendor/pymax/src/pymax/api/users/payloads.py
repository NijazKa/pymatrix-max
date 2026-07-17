from collections.abc import Iterable

from pymax.api.models import CamelModel
from pymax.types.domain import ContactInfo

from .enums import ContactAction


class FetchContactsPayload(CamelModel):
    contact_ids: list[int]


class SearchByPhonePayload(CamelModel):
    phone: str


class ContactActionPayload(CamelModel):
    contact_id: int
    action: ContactAction


class _ContactPayload(CamelModel):
    first_name: str


class ImportContactsPayload(CamelModel):
    contact_list: dict[str, _ContactPayload]  # phone -> contact payload

    @classmethod
    def from_contacts(cls, contacts: Iterable[ContactInfo]) -> "ImportContactsPayload":
        return cls(
            contact_list={
                contact.phone: _ContactPayload(
                    first_name=contact.first_name,
                )
                for contact in contacts
            }
        )
