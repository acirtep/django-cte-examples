from django.contrib import admin
from django.db.models import OuterRef, Subquery, F, Value, Count, Sum, DateField
from django.db.models.expressions import Window, Exists
from django.db.models.functions import Concat, TruncMonth, Coalesce, RowNumber, Cast
from django.db.models.sql.constants import LOUTER
from django.http import HttpRequest
from django_cte import CTE, with_cte
from django_cte.raw import raw_cte_sql

from examples.models import EmployeeReport, GitCommitHistory, Employee, SelectionPeriod


class QueryTypeFilter(admin.SimpleListFilter):
    title = "Query Type"
    parameter_name = "query_type"

    def lookups(self, request, model_admin):
        return (
            ("subquery", "Subquery"),
            ("cte", "CTE"),
            ("cte_cte", "CTE in CTE"),
            ("cte_raw", "CTE and RAW SQL"),
            ("cte_union", "CTE and Union"),
        )

    def queryset(self, request, queryset):
        return queryset


class AggregationTypeFilter(admin.SimpleListFilter):
    title = "Aggregation Type"
    parameter_name = "aggregation_type"

    def lookups(self, request, model_admin):
        return (
            ("reporting_year_month", "Month"),
            ("department_name", "Department"),
            ("month_department", "Month & Department"),
            ("employee_name", "Employee"),
            ("month_employee", "Month & Employee"),
        )

    def queryset(self, request, queryset):
        return queryset


@admin.register(EmployeeReport)
class EmployeeReportAdmin(admin.ModelAdmin):
    change_list_template = "admin/employee_report_change_list.html"

    search_fields = ("employee_name",)
    list_filter = [QueryTypeFilter, AggregationTypeFilter]
    list_per_page = 1
    show_facets = False
    ordering = None

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request: HttpRequest):
        return Employee.objects.prefetch_related("departments").annotate(
            employee_name=Concat(F("first_name"), Value(" "), F("last_name")),
            department_name=F("departments__department_name"),
        )

    def _get_with_subquery(self, qs, aggregation_level):
        number_of_commits_query = (
            GitCommitHistory.objects.filter(author_email=OuterRef("email"))
            .values("author_email")
            .annotate(number_of_commits=Count("id"))
            .values("number_of_commits")
        )

        return (
            qs.annotate(
                employee_name=F("employee_name")
                if "employee_name" in aggregation_level
                else Value("-"),
                department_name=F("department_name")
                if "department_name" in aggregation_level
                else Value("-"),
                reporting_year_month=Value("-"),
            )
            .values("reporting_year_month", "department_name", "employee_name")
            .annotate(
                number_of_commits=Sum(Coalesce(Subquery(number_of_commits_query), 0))
            )
        )

    def _get_with_cte(self, qs, aggregation_level):
        employee_cte = CTE(qs, name="employee_cte")
        git_commit_cte = CTE(
            GitCommitHistory.objects.annotate(
                reporting_year_month=Cast(TruncMonth("commit_date"), DateField())
            )
            .values("reporting_year_month", "author_email")
            .annotate(number_of_commits=Count("id")),
            name="git_commit_cte",
        )

        return with_cte(
            employee_cte,
            git_commit_cte,
            select=git_commit_cte.join(
                employee_cte.queryset(),
                email=git_commit_cte.col.author_email,
            )
            .annotate(
                employee_name=F("employee_name")
                if "employee_name" in aggregation_level
                else Value("-"),
                department_name=F("department_name")
                if "department_name" in aggregation_level
                else Value("-"),
                reporting_year_month=git_commit_cte.col.reporting_year_month
                if "reporting_year_month" in aggregation_level
                else Value("-"),
            )
            .values("reporting_year_month", "department_name", "employee_name")
            .annotate(
                number_of_commits=Sum(Coalesce(git_commit_cte.col.number_of_commits, 0))
            ),
        )

    def _get_with_cte_cte(self, qs, aggregation_level):
        employee_cte = CTE(qs, name="employee_cte")
        git_commit_cte = CTE(
            GitCommitHistory.objects.annotate(
                reporting_year_month=Cast(TruncMonth("commit_date"), DateField())
            )
            .values("reporting_year_month", "author_email")
            .annotate(number_of_commits=Count("id")),
            name="git_commit_cte",
        )
        git_commit_top_cte = CTE(
            with_cte(
                select=git_commit_cte.queryset()
                .annotate(
                    rank=Window(
                        expression=RowNumber(),
                        partition_by=[F("reporting_year_month")],
                        order_by=F("number_of_commits").desc(),
                    )
                )
                .filter(rank=1)
            ),
            name="git_commit_top_cte",
        )

        return with_cte(
            employee_cte,
            git_commit_cte,
            git_commit_top_cte,
            select=git_commit_top_cte.join(
                employee_cte.queryset(),
                email=git_commit_top_cte.col.author_email,
            )
            .annotate(
                employee_name=F("employee_name")
                if "employee_name" in aggregation_level
                else Value("-"),
                department_name=F("department_name")
                if "department_name" in aggregation_level
                else Value("-"),
                reporting_year_month=git_commit_top_cte.col.reporting_year_month
                if "reporting_year_month" in aggregation_level
                else Value("-"),
            )
            .values("reporting_year_month", "department_name", "employee_name")
            .annotate(
                number_of_commits=Sum(
                    Coalesce(git_commit_top_cte.col.number_of_commits, 0)
                )
            ),
        )

    def _get_with_raw_sql(self, qs, aggregation_level):
        selection_period_cte = CTE(
            raw_cte_sql(
                f"""
                    SELECT DATE('2026-01-01') as reporting_date
                    UNION ALL
                    SELECT DATE(reporting_date, '+1 month')
                    FROM selection_period_cte
                    WHERE reporting_date < DATE('now', 'start of month')
                """,
                params=[],
                refs={"reporting_date": DateField()},
            ),
            name=f"selection_period_cte",
        )

        employee_selection_cte = CTE(
            self._get_with_cte(qs=qs, aggregation_level=aggregation_level),
            name="employee_selection_cte",
        )

        return with_cte(
            selection_period_cte,
            employee_selection_cte,
            select=employee_selection_cte.join(
                SelectionPeriod,
                reporting_date=employee_selection_cte.col.reporting_year_month,
                _join_type=LOUTER,
            ).annotate(
                reporting_year_month=F("reporting_date"),
                department_name=Coalesce(
                    employee_selection_cte.col.department_name, Value("-")
                ),
                employee_name=Coalesce(
                    employee_selection_cte.col.employee_name, Value("-")
                ),
                number_of_commits=Coalesce(
                    employee_selection_cte.col.number_of_commits, Value(0)
                ),
            ),
        )

    def _get_with_union(self, qs, aggregation_level):
        employee_cte = CTE(qs.annotate(dummy_id=Value(1)), name="employee_cte")

        selection_period_cte = CTE(
            raw_cte_sql(
                f"""
                            SELECT DATE('2026-01-01') as reporting_date
                            UNION ALL
                            SELECT DATE(reporting_date, '+1 month')
                            FROM selection_period_cte
                            WHERE reporting_date < DATE('now', 'start of month')
                        """,
                params=[],
                refs={"reporting_date": DateField()},
            ),
            name=f"selection_period_cte",
        )

        git_commit_cte = CTE(
            GitCommitHistory.objects.annotate(
                reporting_year_month=Cast(TruncMonth("commit_date"), DateField())
            )
            .values("reporting_year_month", "author_email")
            .annotate(number_of_commits=Count("id")),
            name="git_commit_cte",
        )

        union_cte = CTE(
            (
                employee_cte.join(
                    SelectionPeriod.objects.all().annotate(dummy_id=Value(1)),
                    dummy_id=employee_cte.col.dummy_id,
                )
                .annotate(
                    email=employee_cte.col.email,
                    reporting_year_month=F("reporting_date"),
                    employee_name=employee_cte.col.employee_name,
                    department_name=employee_cte.col.department_name,
                    number_of_commits=Value(0),
                )
                .filter(
                    ~Exists(
                        git_commit_cte.queryset().filter(
                            reporting_year_month=OuterRef("reporting_date"),
                            author_email=OuterRef("email"),
                        )
                    )
                )
                .values(
                    "reporting_year_month",
                    "employee_name",
                    "department_name",
                    "number_of_commits",
                )
                .union(
                    git_commit_cte.join(
                        employee_cte.queryset(),
                        email=git_commit_cte.col.author_email,
                    )
                    .annotate(
                        reporting_year_month=git_commit_cte.col.reporting_year_month,
                        number_of_commits=git_commit_cte.col.number_of_commits,
                    )
                    .values(
                        "reporting_year_month",
                        "employee_name",
                        "department_name",
                        "number_of_commits",
                    )
                )
            ),
            name="union_cte",
        )

        return with_cte(
            selection_period_cte,
            employee_cte,
            git_commit_cte,
            union_cte,
            select=union_cte.queryset()
            .annotate(
                employee_name=F("employee_name")
                if "employee_name" in aggregation_level
                else Value("-"),
                department_name=F("department_name")
                if "department_name" in aggregation_level
                else Value("-"),
                reporting_year_month=F("reporting_year_month")
                if "reporting_year_month" in aggregation_level
                else Value("-"),
            )
            .values("reporting_year_month", "department_name", "employee_name")
            .annotate(number_of_commits=Sum(F("number_of_commits"))),
        )

    def changelist_view(self, request, extra_context=None):

        response = super().changelist_view(
            request,
            extra_context=extra_context,
        )

        try:
            qs = response.context_data["cl"].queryset.order_by()
        except (AttributeError, KeyError):
            return response

        match request.GET.get("aggregation_type"):
            case "reporting_year_month":
                aggregation_level = ["reporting_year_month"]
            case "department_name":
                aggregation_level = ["department_name"]
            case "employee_name":
                aggregation_level = ["employee_name"]
            case "month_department":
                aggregation_level = ["reporting_year_month", "department_name"]
            case "month_employee":
                aggregation_level = ["reporting_year_month", "employee_name"]
            case _:
                aggregation_level = [
                    "reporting_year_month",
                    "department_name",
                    "employee_name",
                ]

        match request.GET.get("query_type"):
            case "subquery":
                qs = self._get_with_subquery(qs=qs, aggregation_level=aggregation_level)
            case "cte":
                qs = self._get_with_cte(qs=qs, aggregation_level=aggregation_level)
            case "cte_cte":
                qs = self._get_with_cte_cte(qs=qs, aggregation_level=aggregation_level)
            case "cte_raw":
                if "reporting_year_month" not in aggregation_level:
                    aggregation_level.append("reporting_year_month")
                qs = self._get_with_raw_sql(qs=qs, aggregation_level=aggregation_level)
            case "cte_union":
                qs = self._get_with_union(qs=qs, aggregation_level=aggregation_level)
            case _:
                qs = self._get_with_cte(qs=qs, aggregation_level=aggregation_level)

        response.context_data["summary"] = list(
            qs.values(
                "reporting_year_month",
                "department_name",
                "employee_name",
                "number_of_commits",
            ).order_by("reporting_year_month", "department_name", "employee_name")
        )

        return response
