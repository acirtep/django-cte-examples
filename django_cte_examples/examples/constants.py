from django.db import models


class DepartmentEnum(models.TextChoices):
    SALES = "Sales", "Sales"
    IT = "IT", "IT"
    HR = "HR", "HR"
