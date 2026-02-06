import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DollarSign, Users, Briefcase, Activity, TrendingUp, ArrowUpRight, ArrowDownRight, FileText, Percent, Mail } from 'lucide-react';
import { Button } from "@/components/ui/button";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend } from 'recharts';
import N8nHealth from './N8nHealth';
import DocumentFeed from './DocumentFeed';

const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884d8'];

const StatsOverview = () => {
    const [stats, setStats] = useState({
        totalCases: 0,
        activeCases: 0,
        totalRevenue: 0,
        totalSavings: 0,
        totalEmails: 0,
        winRate: 0,
        avgCaseValue: 0,
        latestCaseId: null
    });
    const [charts, setCharts] = useState({
        revenue: [],
        status: [],
        negotiationPerf: [],
        negotiationResults: []
    });
    const [n8nExecutions, setN8nExecutions] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchData = async () => {
            try {
                const [casesRes, n8nRes] = await Promise.all([
                    fetch('/internal-api/cases'),
                    fetch('/internal-api/integrations/n8n/executions')
                ]);

                if (casesRes.ok) {
                    const cases = await casesRes.json();

                    // KPI Calculations
                    const totalCases = cases.length;
                    const activeCases = cases.filter(c => c.status === 'Active').length;
                    const totalRevenue = cases.reduce((acc, c) => acc + (c.revenue || 0), 0);
                    const totalSavings = cases.reduce((acc, c) => acc + (c.savings || 0), 0);
                    const totalEmails = cases.reduce((acc, c) => acc + (c.emails_received || 0) + (c.emails_sent || 0), 0);
                    const winRate = totalCases > 0 ? (activeCases / totalCases) * 100 : 0; // Simplified "Win" definition
                    const avgCaseValue = totalCases > 0 ? totalRevenue / totalCases : 0;
                    const latestCaseId = totalCases > 0 ? cases[0].id : null;

                    // Chart 1: Revenue per Case (Existing)
                    const revenueData = cases.map(c => ({
                        name: c.case_name ? (c.case_name.substring(0, 10) + '...') : c.id,
                        revenue: c.revenue || 0,
                        savings: c.savings || 0,
                        fees: c.fees_taken || 0
                    }));

                    // Chart 2: Status Distribution
                    const statusCounts = cases.reduce((acc, c) => {
                        acc[c.status] = (acc[c.status] || 0) + 1;
                        return acc;
                    }, {});
                    const statusData = Object.entries(statusCounts).map(([name, value]) => ({ name, value }));

                    // Chart 3 & 4: Negotiation Data (Flattened)
                    let negotiations = [];
                    cases.forEach(c => {
                        if (c.negotiations) {
                            negotiations = [...negotiations, ...c.negotiations];
                        }
                    });

                    const negotiationPerf = negotiations.map((n, i) => {
                        const name = n.to ? n.to.substring(0, 10) : ('Neg ' + i);
                        return {
                            name,
                            offered: n.offered_bill || 0,
                            actual: n.actual_bill || 0
                        };
                    }).slice(0, 20);

                    const negResults = negotiations.reduce((acc, n) => {
                        const res = n.result || 'Unknown';
                        acc[res] = (acc[res] || 0) + 1;
                        return acc;
                    }, {});
                    const negotiationResults = Object.entries(negResults).map(([name, value]) => ({ name, value }));

                    setStats({ totalCases, activeCases, totalRevenue, totalSavings, totalEmails, winRate, avgCaseValue, latestCaseId });
                    setCharts({ revenue: revenueData, status: statusData, negotiationPerf, negotiationResults });
                }

                if (n8nRes.ok) {
                    const n8nData = await n8nRes.json();
                    if (Array.isArray(n8nData)) {
                        setN8nExecutions(n8nData);
                    }
                }

            } catch (error) {
                console.error("Failed to fetch dashboard data:", error);
            } finally {
                setLoading(false);
            }
        };

        fetchData();
    }, []);

    const kpiCards = [
        { title: "Total Revenue", value: "$" + stats.totalRevenue.toLocaleString(), icon: DollarSign, color: "text-green-500", desc: "Gross revenue" },
        { title: "Potential Savings", value: "$" + stats.totalSavings.toLocaleString(), icon: TrendingUp, color: "text-blue-500", desc: "Total negotiated savings" },
        { title: "Active Cases", value: stats.activeCases, icon: Activity, color: "text-purple-500", desc: stats.totalCases + " total cases" },
        { title: "Win Rate", value: stats.winRate.toFixed(1) + "%", icon: Percent, color: "text-indigo-500", desc: "Active / Total Ratio" },
        { title: "Emails Processed", value: stats.totalEmails, icon: Mail, color: "text-orange-500", desc: "Total volume" },
        { title: "Avg Case Value", value: "$" + stats.avgCaseValue.toLocaleString(undefined, { maximumFractionDigits: 0 }), icon: DollarSign, color: "text-emerald-600", desc: "Revenue per case" },
    ];

    if (loading) {
        return <div className="p-8 text-center text-muted-foreground animate-pulse">Loading dashboard...</div>;
    }

    return (
        <div className="space-y-6">
            <h2 className="text-3xl font-bold tracking-tight">Executive Dashboard</h2>

            {/* Top Row: KPI Cards */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">
                            Total Cases
                        </CardTitle>
                        <Briefcase className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{stats.totalCases}</div>
                        <p className="text-xs text-muted-foreground">
                            Active database records
                        </p>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">
                            Total Emails
                        </CardTitle>
                        <Mail className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{stats.totalEmails}</div>
                        <p className="text-xs text-muted-foreground">
                            Sent and received
                        </p>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">
                            Total Savings
                        </CardTitle>
                        <TrendingUp className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">
                            ${stats.totalSavings.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        </div>
                        <p className="text-xs text-muted-foreground">
                            Negotiated reductions
                        </p>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">
                            Total Revenue
                        </CardTitle>
                        <DollarSign className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">
                            ${stats.totalRevenue.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        </div>
                        <p className="text-xs text-muted-foreground">
                            Fees collected
                        </p>
                    </CardContent>
                </Card>
            </div>

            {/* Middle Row: N8n Health & Document Feed */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                <N8nHealth executions={n8nExecutions} loading={loading} />
                <DocumentFeed latestCaseId={stats.latestCaseId} />
                {/* Note: using chart data name is a hack, better to use stats.latestCaseId if available. 
                    Let's check setStats... it doesn't store the raw list. 
                    I'll need to store a raw case ID in stats or use a separate state.
                */}
            </div>

            {/* Bottom Row: Charts & Logs */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-7">
                {/* Main Graph: Revenue Stacked */}
                <Card className="col-span-4">
                    <CardHeader>
                        <CardTitle>Financial Overview (Revenue vs Savings)</CardTitle>
                    </CardHeader>
                    <CardContent className="pl-2">
                        <div className="h-[300px] w-full">
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart data={charts.revenue}>
                                    <CartesianGrid strokeDasharray="3 3" />
                                    <XAxis dataKey="name" />
                                    <YAxis />
                                    <Tooltip contentStyle={{ backgroundColor: 'hsl(var(--card))' }} />
                                    <Legend />
                                    <Bar dataKey="revenue" stackId="a" fill="#10b981" name="Revenue" />
                                    <Bar dataKey="savings" stackId="a" fill="#3b82f6" name="Savings" />
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    </CardContent>
                </Card>

                {/* Status Pie */}
                <Card className="col-span-3">
                    <CardHeader>
                        <CardTitle>Case Status Distribution</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="h-[300px] w-full">
                            <ResponsiveContainer width="100%" height="100%">
                                <PieChart>
                                    <Pie
                                        data={charts.status}
                                        cx="50%"
                                        cy="50%"
                                        innerRadius={60}
                                        outerRadius={80}
                                        paddingAngle={5}
                                        dataKey="value"
                                    >
                                        {charts.status.map((entry, index) => (
                                            <Cell key={'cell-' + index} fill={COLORS[index % COLORS.length]} />
                                        ))}
                                    </Pie>
                                    <Tooltip />
                                    <Legend />
                                </PieChart>
                            </ResponsiveContainer>
                        </div>
                    </CardContent>
                </Card>
            </div>

            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-7">
                {/* Negotiation Performance */}
                <Card className="col-span-4">
                    <CardHeader>
                        <CardTitle>Negotiation Savings (Offered vs Actual)</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="h-[300px] w-full">
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart data={charts.negotiationPerf}>
                                    <CartesianGrid strokeDasharray="3 3" />
                                    <XAxis dataKey="name" />
                                    <YAxis />
                                    <Tooltip />
                                    <Legend />
                                    <Bar dataKey="offered" fill="#94a3b8" name="Original Bill" />
                                    <Bar dataKey="actual" fill="#22c55e" name="Settled Amount" />
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    </CardContent>
                </Card>

                {/* Negotiation Results Donut */}
                <Card className="col-span-3">
                    <CardHeader>
                        <CardTitle>Negotiation Outcomes</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="h-[300px] w-full flex items-center justify-center">
                            {charts.negotiationResults.length > 0 ? (
                                <ResponsiveContainer width="100%" height="100%">
                                    <PieChart>
                                        <Pie
                                            data={charts.negotiationResults}
                                            innerRadius={60}
                                            outerRadius={80}
                                            paddingAngle={5}
                                            dataKey="value"
                                        >
                                            {charts.negotiationResults.map((entry, index) => (
                                                <Cell key={'cell-' + index} fill={COLORS[index % COLORS.length]} />
                                            ))}
                                        </Pie>
                                        <Tooltip />
                                        <Legend />
                                    </PieChart>
                                </ResponsiveContainer>
                            ) : (
                                <div className="text-muted-foreground">No negotiation data yet</div>
                            )}
                        </div>
                    </CardContent>
                </Card>
            </div>


        </div>
    );
};

export default StatsOverview;
