from pydantic import BaseModel


class StoryTemplate(BaseModel):
    id: str
    name: str
    genre: str
    short_description: str
    tags: list[str]
    recommended_tone: list[str]


class TemplatesResponse(BaseModel):
    templates: list[StoryTemplate]
