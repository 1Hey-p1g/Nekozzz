"""Tender context is session-only, independent of permanent personnel data."""
from dataclasses import dataclass, field
from pathlib import Path
from config.paths import resource_path


@dataclass
class PersonAutoFillEntry:
    person_id: int
    display_name: str
    role_text: str = ''
    table_certificate_ids: set[int] = field(default_factory=set)
    table_project_ids: set[int] = field(default_factory=set)  # 人员业绩关系ID, not 工程ID.
    attachment_certificate_ids: set[int] = field(default_factory=set)


@dataclass
class PersonAutoFillTask:
    template_path: Path = field(default_factory=lambda: resource_path('resources/templates/personnel_table.docx'))
    include_title: bool = False
    title_text: str = ''
    include_note: bool = False
    note_text: str = ''
    shrink_wide_tables: bool = True
    people: list[PersonAutoFillEntry] = field(default_factory=list)

    def item(self, person_id):
        return next((p for p in self.people if p.person_id == person_id), None)

    def add(self, person_id, name):
        if self.item(person_id):
            return False
        self.people.append(PersonAutoFillEntry(person_id, name))
        return True

    def remove(self, person_id):
        self.people = [p for p in self.people if p.person_id != person_id]

    def reorder(self, ids):
        if len(ids) != len(self.people) or set(ids) != {p.person_id for p in self.people}:
            raise ValueError('任务人员顺序无效')
        by_id = {p.person_id: p for p in self.people}
        self.people = [by_id[i] for i in ids]
