/** @odoo-module */
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";

export class OwlHomeFinanceDashboard extends Component {
    setup() {
        const currentYear = new Date().getFullYear();
        const startDate = `${currentYear}-01-01`;
        const endDate = `${currentYear}-12-31`;

        this.state = useState({
            selectedStartDate: startDate,
            selectedEndDate: endDate,
            employees:[],
            workingSchedule:[],
            selectedWorkingSchedule:"",
            selectedEmployee:"",
            tableDataItems:[],
            employeeWarnings:[],
             employeeStatsData:[],
        });

        this.orm = useService('orm');

        onWillStart(async () => {
            this.state.isLoading = true;
            try {
                await Promise.all([
                    await this.fetchDashboardData()
                ]);
            } catch (error) {
                console.error("Error during initial dashboard data fetch:", error);
            } finally {
                this.state.isLoading = false;
            }
        });
    }

    async fetchDashboardData() {
        await Promise.all([
        await this.getEmployees(),
        await this.getEmployeesWorkingSchedule(),
        await this.fetchAttendanceSummaryReport(),
        await this.fetchEmployeeWarningSummaryReport()
        ]);
    }
    async onChangeFilter() {
        this.state.isLoading = true;
        try {
            await this.fetchDashboardData();
        } catch (error) {
            console.error("Error fetching dashboard data after filter change:", error);
        } finally {
            this.state.isLoading = false;
        }
    }

    async onChangeStartDate(ev) {
        this.state.selectedStartDate = ev.target.value;
        await this.onChangeFilter();
    }
    async onChangeSelectedEmployee(ev) {
        this.state.selectedEmployee = ev.target.value;
        await this.onChangeFilter();
    }
    async onChangeSelectedWorkingSchedule(ev) {
        this.state.selectedWorkingSchedule = ev.target.value;
        await this.onChangeFilter();
    }
    async onChangeEndDate(ev) {
        this.state.selectedEndDate = ev.target.value;
        await this.onChangeFilter();
    }

    async getEmployees(){
    const employeeList = await this.orm.searchRead("hr.employee",[],["id","name"])
    this.state.employees = employeeList
    }
    async getEmployeesWorkingSchedule(){
    const scheduleList = await this.orm.searchRead("resource.calendar",[],["id","name"])
    this.state.workingSchedule = scheduleList
    }

    async fetchAttendanceSummaryReport() {
    this.state.isLoading = true;
    const startDate = this.state.selectedStartDate;
    const endDate = this.state.selectedEndDate;

    try {
        const result = await this.orm.call(
            "dilek.biometric_attendance.report",
            "get_attendance_report_analysis",
            [[]],
            {
                startDate: startDate,
                endDate: endDate,

            }
        );

        if (result) {
            // Assign the list directly to your state
            this.state.tableDataItems = result;
            console.log("Data loaded successfully:", result);
        } else {
            this.state.tableDataItems = [];
        }
    } catch (error) {
        console.error("Error loading budget data:", error);
        this.state.tableDataItems = [];
    } finally {
        this.state.isLoading = false;
    }
}

    async fetchEmployeeWarningSummaryReport() {
    this.state.isLoading = true;
    const startDate = this.state.selectedStartDate;
    const endDate = this.state.selectedEndDate;

    try {
        const result = await this.orm.call(
            "dilek.biometric_attendance.report",
            "get_staff_reporting_data_check",
            [[]],
            {
                startDate: startDate,
                endDate: endDate,

            }
        );

        if (result) {
            // Assign the list directly to your state
            this.state.employeeWarnings = result[0];
             this.state.employeeStatsData = result[1];
            console.log("Data loaded successfully:", result);
        } else {
            this.state.employeeWarnings = [];
        }
    } catch (error) {
        console.error("Error loading budget data:", error);
        this.state.employeeWarnings = [];
    } finally {
        this.state.isLoading = false;
    }
}
}

OwlHomeFinanceDashboard.template = "owl.OwlHomeFinanceDashboard";
registry.category("actions").add("owl.home_finance_dashboard", OwlHomeFinanceDashboard);