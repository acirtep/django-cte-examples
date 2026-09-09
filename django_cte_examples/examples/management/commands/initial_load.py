from datetime import date, timezone, tzinfo, UTC


from django.core.management.base import BaseCommand
from django.db.models import Model
from django.db.models.functions import Mod, Random
from faker import Faker

from examples.constants import DepartmentEnum
from examples.models import Department, Employee, GitCommitHistory


class Command(BaseCommand):
    help = "Initial load data"

    def load_department(self):
        for department_name in DepartmentEnum.choices:
            Department.objects.get_or_create(department_name=department_name[0])

    def load_employee(self, fake):
        Employee.objects.all().delete()
        employee_objs = [
            Employee(
                id=i,
                email=fake.email(),
                first_name=fake.first_name(),
                last_name=fake.last_name(),
            )
            for i in range(1, 201)
        ]

        Employee.objects.bulk_create(employee_objs)

        it_department_obj = Department.objects.get(department_name=DepartmentEnum.IT)
        for employee_obj in Employee.objects.annotate(mod_3=Mod("id", 3)).filter(
            mod_3=0
        ):
            employee_obj.departments.add(it_department_obj)

        sales_department_obj = Department.objects.get(
            department_name=DepartmentEnum.SALES
        )
        for employee_obj in Employee.objects.annotate(mod_3=Mod("id", 3)).filter(
            mod_3=1
        ):
            employee_obj.departments.add(sales_department_obj)

        hr_department_obj = Department.objects.get(department_name=DepartmentEnum.HR)
        for employee_obj in (
            Employee.objects.annotate(mod_3=Mod("id", 3))
            .filter(mod_3=2)
            .order_by("id")[:5]
        ):
            employee_obj.departments.add(hr_department_obj)

        for employee_obj in (
            Employee.objects.annotate(mod_3=Mod("id", 3))
            .filter(mod_3=2)
            .order_by("id")[5:]
        ):
            employee_obj.departments.add(it_department_obj)

    def load_git_commit_history(self, fake):
        GitCommitHistory.objects.all().delete()
        git_commit_history_objs = [
            GitCommitHistory(
                id=i,
                commit_sha=fake.hexify("^" * 40),
                author_email=Employee.objects.prefetch_related("departments")
                .filter(
                    departments__department_name__in=[
                        DepartmentEnum.IT,
                        DepartmentEnum.SALES,
                    ]
                )
                .annotate(random=Random())
                .order_by("random")
                .first()
                .email,
                commit_date=fake.date_time_between(
                    start_date=date(2026, 3, 1), tzinfo=UTC
                ),
                commit_message=fake.sentence(nb_words=6),
            )
            for i in range(1, 10000)
        ]

        GitCommitHistory.objects.bulk_create(git_commit_history_objs)

    def handle(self, *args, **options):
        fake = Faker()
        fake.seed_instance(4321)

        print(f"Loading department data...")
        self.load_department()

        print(f"Loading employee data...")
        self.load_employee(fake=fake)

        print(f"Loading git commit history data...")
        self.load_git_commit_history(fake=fake)
