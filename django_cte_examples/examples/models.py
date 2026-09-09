from django.db import models

from examples.constants import DepartmentEnum


class Employee(models.Model):
    email = models.EmailField(unique=True)
    first_name = models.CharField(null=False, blank=False)
    last_name = models.CharField(null=False, blank=False)

    departments = models.ManyToManyField(to="Department", blank=True)

    def __str__(self) -> str:
        return self.email


class Department(models.Model):
    department_name = models.CharField(
        choices=DepartmentEnum.choices, null=False, blank=False, unique=True
    )

    def __str__(self) -> str:
        return self.department_name


class GitCommitHistory(models.Model):
    commit_sha = models.CharField(null=False, blank=False, unique=True)
    author_email = models.EmailField(null=False, blank=False)
    commit_date = models.DateTimeField(null=False, blank=False)
    commit_message = models.CharField(null=True)


class EmployeeReport(models.Model):
    reporting_year_month = models.CharField(null=False, blank=False)
    employee_name = models.CharField(null=False, blank=False)
    department_name = models.CharField(null=False, blank=False)
    number_of_commits = models.IntegerField(null=False, blank=False)

    class Meta:
        managed = False


class SelectionPeriod(models.Model):
    reporting_date = models.DateField(primary_key=True)

    class Meta:
        managed = False
        db_table = "selection_period_cte"
