import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid } from 'recharts';

const COLORS = ['#10b981', '#ef4444', '#3b82f6', '#f59e0b', '#8b5cf6', '#06b6d4', '#ec4899'];

const N8nExecutions = () => {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        const fetchData = async () => {
            try {
                const res = await fetch('/internal-api/integrations/n8n/executions');
                if (res.ok) {
                    const d = await res.json();
                    if (d.error) setError(d.error);
                    else setData(d);
                } else if (res.status === 400) {
                    setError("n8n API Key not configured. Go to Settings to add it.");
                } else {
                    setError("Failed to fetch n8n data");
                }
            } catch (err) {
                setError("Failed to connect to n8n API");
            } finally {
                setLoading(false);
            }
        };
        fetchData();
    }, []);

    if (loading) return <div className="p-8 text-muted-foreground">Loading n8n data...</div>;

    if (error) {
        return (
            <div className="space-y-6">
                <h2 className="text-3xl font-bold tracking-tight">n8n Executions</h2>
                <Card><CardContent className="p-6"><div className="text-muted-foreground">{error}</div></CardContent></Card>
            </div>
        );
    }

    if (!data) return null;

    const successRate = data.total_fetched > 0 ? ((data.success / data.total_fetched) * 100).toFixed(1) : 0;

    // Status pie data
    const statusData = [
        data.success > 0 && { name: 'Success', value: data.success },
        data.error > 0 && { name: 'Error', value: data.error },
        data.running > 0 && { name: 'Running', value: data.running },
        data.waiting > 0 && { name: 'Waiting', value: data.waiting },
    ].filter(Boolean);

    // Workflow breakdown bar data
    const workflowData = data.workflow_breakdown
        ? Object.entries(data.workflow_breakdown)
            .map(([name, value]) => ({ name: name.length > 20 ? name.substring(0, 20) + '...' : name, value, fullName: name }))
            .sort((a, b) => b.value - a.value)
        : [];

    return (
        <div className="space-y-6">
            <h2 className="text-3xl font-bold tracking-tight">n8n Executions</h2>

            {/* KPI Cards */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Total Executions</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{data.total_fetched}</div>
                        <p className="text-xs text-muted-foreground">Last 50 fetched</p>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Successful</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold text-green-600">{data.success}</div>
                        <p className="text-xs text-muted-foreground">{successRate}% success rate</p>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Errors</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold text-red-600">{data.error}</div>
                        <p className="text-xs text-muted-foreground">Failed executions</p>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Running</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold text-blue-600">{data.running || 0}</div>
                        <p className="text-xs text-muted-foreground">Currently active</p>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Workflows</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{workflowData.length}</div>
                        <p className="text-xs text-muted-foreground">Unique workflows</p>
                    </CardContent>
                </Card>
            </div>

            {/* Charts */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-7">
                {/* Workflow Breakdown */}
                <Card className="col-span-4">
                    <CardHeader>
                        <CardTitle>Executions by Workflow</CardTitle>
                        <CardDescription>Number of runs per workflow</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="h-[300px] w-full">
                            {workflowData.length > 0 ? (
                                <ResponsiveContainer width="100%" height="100%">
                                    <BarChart data={workflowData} layout="vertical">
                                        <CartesianGrid strokeDasharray="3 3" />
                                        <XAxis type="number" />
                                        <YAxis dataKey="name" type="category" width={140} tick={{ fontSize: 11 }} />
                                        <Tooltip
                                            contentStyle={{ backgroundColor: 'hsl(var(--card))' }}
                                            formatter={(v, _, props) => [v, props.payload.fullName || 'Executions']}
                                        />
                                        <Bar dataKey="value" fill="#8b5cf6" name="Executions" />
                                    </BarChart>
                                </ResponsiveContainer>
                            ) : (
                                <div className="h-full flex items-center justify-center text-muted-foreground">No workflow data</div>
                            )}
                        </div>
                    </CardContent>
                </Card>

                {/* Status Pie */}
                <Card className="col-span-3">
                    <CardHeader>
                        <CardTitle>Execution Status</CardTitle>
                        <CardDescription>Success vs Error distribution</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="h-[300px] w-full">
                            {statusData.length > 0 ? (
                                <ResponsiveContainer width="100%" height="100%">
                                    <PieChart>
                                        <Pie data={statusData} cx="50%" cy="50%" innerRadius={60} outerRadius={80} paddingAngle={5} dataKey="value">
                                            {statusData.map((_, i) => <Cell key={'cell-' + i} fill={COLORS[i % COLORS.length]} />)}
                                        </Pie>
                                        <Tooltip />
                                        <Legend />
                                    </PieChart>
                                </ResponsiveContainer>
                            ) : (
                                <div className="h-full flex items-center justify-center text-muted-foreground">No data</div>
                            )}
                        </div>
                    </CardContent>
                </Card>
            </div>

            {/* Executions Table */}
            <Card>
                <CardHeader>
                    <CardTitle>Recent Executions</CardTitle>
                    <CardDescription>Last 20 workflow executions</CardDescription>
                </CardHeader>
                <CardContent>
                    <div className="border rounded-md overflow-auto">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="bg-muted">
                                    <th className="p-3 text-left font-medium">ID</th>
                                    <th className="p-3 text-left font-medium">Workflow</th>
                                    <th className="p-3 text-left font-medium">Status</th>
                                    <th className="p-3 text-left font-medium">Mode</th>
                                    <th className="p-3 text-right font-medium">Duration</th>
                                    <th className="p-3 text-left font-medium">Started</th>
                                </tr>
                            </thead>
                            <tbody>
                                {data.recent_executions?.length > 0 ? (
                                    data.recent_executions.map((exec) => (
                                        <tr key={exec.id} className="border-t hover:bg-muted/50">
                                            <td className="p-3 font-mono text-xs">{exec.id}</td>
                                            <td className="p-3 text-xs max-w-[200px] truncate" title={exec.workflowName || exec.workflowId}>
                                                {exec.workflowName || exec.workflowId || '-'}
                                            </td>
                                            <td className="p-3">
                                                <span className={
                                                    exec.status === 'success' ? 'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800' :
                                                    exec.status === 'error' ? 'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800' :
                                                    exec.status === 'running' ? 'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800' :
                                                    'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800'
                                                }>
                                                    {exec.finished ? (exec.status || 'success') : (exec.status || 'running')}
                                                </span>
                                            </td>
                                            <td className="p-3 text-xs text-muted-foreground capitalize">{exec.mode || '-'}</td>
                                            <td className="p-3 text-right text-xs">
                                                {exec.duration_sec != null ? `${exec.duration_sec}s` : '-'}
                                            </td>
                                            <td className="p-3 text-xs text-muted-foreground">
                                                {exec.startedAt ? new Date(exec.startedAt).toLocaleString() : '-'}
                                            </td>
                                        </tr>
                                    ))
                                ) : (
                                    <tr><td colSpan={6} className="p-4 text-center text-muted-foreground">No recent executions</td></tr>
                                )}
                            </tbody>
                        </table>
                    </div>
                </CardContent>
            </Card>
        </div>
    );
};

export default N8nExecutions;
