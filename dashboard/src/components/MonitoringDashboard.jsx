import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { RefreshCw } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, PieChart, Pie, Cell, Legend } from 'recharts';

const COLORS = ['#10b981', '#ef4444', '#3b82f6', '#f59e0b', '#8b5cf6', '#06b6d4', '#ec4899'];

const MonitoringDashboard = () => {
    const [tokenUsage, setTokenUsage] = useState([]);
    const [openAiStats, setOpenAiStats] = useState(null);
    const [n8nStats, setN8nStats] = useState(null);
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);

    const fetchData = async (isRefresh = false) => {
        if (isRefresh) setRefreshing(true);
        else setLoading(true);
        try {
            const [usageRes, openaiRes, n8nRes] = await Promise.all([
                fetch('/internal-api/token_usage'),
                fetch('/internal-api/integrations/openai/usage'),
                fetch('/internal-api/integrations/n8n/executions'),
            ]);
            if (usageRes.ok) {
                const data = await usageRes.json();
                setTokenUsage(data.map(item => ({ ...item, dateStr: new Date(item.date).toLocaleDateString() })));
            }
            if (openaiRes.ok) setOpenAiStats(await openaiRes.json());
            if (n8nRes.ok) setN8nStats(await n8nRes.json());
        } catch (error) {
            console.error("Failed to fetch monitoring data:", error);
        } finally {
            setLoading(false);
            setRefreshing(false);
        }
    };

    useEffect(() => { fetchData(); }, []);

    const totalInternalCost = tokenUsage.reduce((acc, curr) => acc + curr.cost, 0);

    // n8n chart data
    const n8nStatusData = n8nStats ? [
        n8nStats.success > 0 && { name: 'Success', value: n8nStats.success },
        n8nStats.error > 0 && { name: 'Error', value: n8nStats.error },
        n8nStats.running > 0 && { name: 'Running', value: n8nStats.running },
        n8nStats.waiting > 0 && { name: 'Waiting', value: n8nStats.waiting },
    ].filter(Boolean) : [];

    const n8nWorkflowData = n8nStats?.workflow_breakdown
        ? Object.entries(n8nStats.workflow_breakdown)
            .map(([name, value]) => ({ name: name.length > 25 ? name.substring(0, 25) + '...' : name, value, fullName: name }))
            .sort((a, b) => b.value - a.value)
        : [];

    const n8nSuccessRate = n8nStats?.total_fetched > 0 ? ((n8nStats.success / n8nStats.total_fetched) * 100).toFixed(1) : 0;

    if (loading) return <div className="p-8 text-muted-foreground">Loading monitoring data...</div>;

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-3xl font-bold tracking-tight">Usage & Costs</h2>
                    <p className="text-sm text-muted-foreground mt-1">
                        Token usage, OpenAI costs, n8n workflow executions, and system spending.
                    </p>
                </div>
                <button onClick={() => fetchData(true)}
                    className="inline-flex items-center gap-2 rounded-md border px-3 py-2 text-sm hover:bg-muted transition-colors">
                    <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} /> Refresh
                </button>
            </div>

            <Tabs defaultValue="overview" className="space-y-4">
                <TabsList>
                    <TabsTrigger value="overview">Cost Overview</TabsTrigger>
                    <TabsTrigger value="n8n">n8n Workflows</TabsTrigger>
                    <TabsTrigger value="openai">OpenAI Usage</TabsTrigger>
                </TabsList>

                {/* ── Cost Overview ── */}
                <TabsContent value="overview" className="space-y-4">
                    <div className="grid gap-4 md:grid-cols-3">
                        <Card>
                            <CardHeader><CardTitle className="text-sm font-medium">Internal Token Cost</CardTitle></CardHeader>
                            <CardContent>
                                <div className="text-3xl font-bold">${totalInternalCost.toFixed(4)}</div>
                                <p className="text-xs text-muted-foreground mt-1">Based on local token logs</p>
                            </CardContent>
                        </Card>
                        <Card>
                            <CardHeader><CardTitle className="text-sm font-medium">n8n Executions</CardTitle></CardHeader>
                            <CardContent>
                                <div className="text-3xl font-bold">{n8nStats?.total_fetched || 0}</div>
                                <p className="text-xs text-muted-foreground mt-1">
                                    {n8nStats?.success || 0} success, {n8nStats?.error || 0} errors
                                </p>
                            </CardContent>
                        </Card>
                        <Card>
                            <CardHeader><CardTitle className="text-sm font-medium">OpenAI API</CardTitle></CardHeader>
                            <CardContent>
                                <div className="text-3xl font-bold">
                                    {openAiStats?.total_usage ? `$${(openAiStats.total_usage / 100).toFixed(2)}` : 'N/A'}
                                </div>
                                <p className="text-xs text-muted-foreground mt-1">Live from OpenAI (if key set)</p>
                            </CardContent>
                        </Card>
                    </div>

                    <Card>
                        <CardHeader>
                            <CardTitle>Daily Token Cost Trend</CardTitle>
                            <CardDescription>Internal AI token spending per day</CardDescription>
                        </CardHeader>
                        <CardContent>
                            <div className="h-[300px] w-full">
                                {tokenUsage.length > 0 ? (
                                    <ResponsiveContainer width="100%" height="100%">
                                        <LineChart data={tokenUsage}>
                                            <CartesianGrid strokeDasharray="3 3" />
                                            <XAxis dataKey="dateStr" />
                                            <YAxis />
                                            <Tooltip contentStyle={{ backgroundColor: 'hsl(var(--card))' }}
                                                formatter={(value) => [`$${value.toFixed(4)}`, 'Cost']} />
                                            <Line type="monotone" dataKey="cost" stroke="#8b5cf6" strokeWidth={2} dot={false} />
                                        </LineChart>
                                    </ResponsiveContainer>
                                ) : <div className="h-full flex items-center justify-center text-muted-foreground">No token usage data yet</div>}
                            </div>
                        </CardContent>
                    </Card>
                </TabsContent>

                {/* ── n8n Workflows ── */}
                <TabsContent value="n8n" className="space-y-4">
                    {n8nStats?.error ? (
                        <Card><CardContent className="p-6"><div className="text-muted-foreground">{n8nStats.error}</div></CardContent></Card>
                    ) : n8nStats ? (
                        <>
                            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                                <Card>
                                    <CardHeader className="pb-2"><CardTitle className="text-sm font-medium">Total Executions</CardTitle></CardHeader>
                                    <CardContent>
                                        <div className="text-2xl font-bold">{n8nStats.total_fetched}</div>
                                        <p className="text-xs text-muted-foreground">Last 50 fetched</p>
                                    </CardContent>
                                </Card>
                                <Card>
                                    <CardHeader className="pb-2"><CardTitle className="text-sm font-medium">Successful</CardTitle></CardHeader>
                                    <CardContent>
                                        <div className="text-2xl font-bold text-green-600">{n8nStats.success}</div>
                                        <p className="text-xs text-muted-foreground">{n8nSuccessRate}% success rate</p>
                                    </CardContent>
                                </Card>
                                <Card>
                                    <CardHeader className="pb-2"><CardTitle className="text-sm font-medium">Errors</CardTitle></CardHeader>
                                    <CardContent>
                                        <div className="text-2xl font-bold text-red-600">{n8nStats.error}</div>
                                    </CardContent>
                                </Card>
                                <Card>
                                    <CardHeader className="pb-2"><CardTitle className="text-sm font-medium">Workflows</CardTitle></CardHeader>
                                    <CardContent>
                                        <div className="text-2xl font-bold">{n8nWorkflowData.length}</div>
                                        <p className="text-xs text-muted-foreground">Unique workflows</p>
                                    </CardContent>
                                </Card>
                            </div>

                            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-7">
                                <Card className="col-span-4">
                                    <CardHeader>
                                        <CardTitle>Executions by Workflow</CardTitle>
                                    </CardHeader>
                                    <CardContent>
                                        <div className="h-[300px] w-full">
                                            {n8nWorkflowData.length > 0 ? (
                                                <ResponsiveContainer width="100%" height="100%">
                                                    <BarChart data={n8nWorkflowData} layout="vertical">
                                                        <CartesianGrid strokeDasharray="3 3" />
                                                        <XAxis type="number" />
                                                        <YAxis dataKey="name" type="category" width={140} tick={{ fontSize: 11 }} />
                                                        <Tooltip contentStyle={{ backgroundColor: 'hsl(var(--card))' }}
                                                            formatter={(v, _, props) => [v, props.payload.fullName || 'Executions']} />
                                                        <Bar dataKey="value" fill="#8b5cf6" name="Executions" />
                                                    </BarChart>
                                                </ResponsiveContainer>
                                            ) : <div className="h-full flex items-center justify-center text-muted-foreground">No workflow data</div>}
                                        </div>
                                    </CardContent>
                                </Card>
                                <Card className="col-span-3">
                                    <CardHeader>
                                        <CardTitle>Execution Status</CardTitle>
                                    </CardHeader>
                                    <CardContent>
                                        <div className="h-[300px] w-full">
                                            {n8nStatusData.length > 0 ? (
                                                <ResponsiveContainer width="100%" height="100%">
                                                    <PieChart>
                                                        <Pie data={n8nStatusData} cx="50%" cy="50%" innerRadius={60} outerRadius={80} paddingAngle={5} dataKey="value">
                                                            {n8nStatusData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                                                        </Pie>
                                                        <Tooltip /><Legend />
                                                    </PieChart>
                                                </ResponsiveContainer>
                                            ) : <div className="h-full flex items-center justify-center text-muted-foreground">No data</div>}
                                        </div>
                                    </CardContent>
                                </Card>
                            </div>

                            {/* Recent Executions Table */}
                            <Card>
                                <CardHeader>
                                    <CardTitle>Recent Executions</CardTitle>
                                    <CardDescription>Last 20 workflow runs</CardDescription>
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
                                                {n8nStats.recent_executions?.length > 0 ? n8nStats.recent_executions.map((exec) => (
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
                                                        <td className="p-3 text-right text-xs">{exec.duration_sec != null ? `${exec.duration_sec}s` : '-'}</td>
                                                        <td className="p-3 text-xs text-muted-foreground">
                                                            {exec.startedAt ? new Date(exec.startedAt).toLocaleString() : '-'}
                                                        </td>
                                                    </tr>
                                                )) : <tr><td colSpan={6} className="p-4 text-center text-muted-foreground">No recent executions</td></tr>}
                                            </tbody>
                                        </table>
                                    </div>
                                </CardContent>
                            </Card>
                        </>
                    ) : <Card><CardContent className="p-6 text-muted-foreground">n8n key/URL not configured. Check Settings.</CardContent></Card>}
                </TabsContent>

                {/* ── OpenAI Usage ── */}
                <TabsContent value="openai" className="space-y-4">
                    <Card>
                        <CardHeader>
                            <CardTitle>OpenAI Live Stats</CardTitle>
                            <CardDescription>Live data from OpenAI API. Requires Admin/Org API key in Settings.</CardDescription>
                        </CardHeader>
                        <CardContent>
                            <pre className="bg-muted p-4 rounded-md overflow-auto max-h-[500px] text-sm">
                                {openAiStats ? JSON.stringify(openAiStats, null, 2) : "No data available. Check your OpenAI API key in Settings."}
                            </pre>
                        </CardContent>
                    </Card>
                </TabsContent>
            </Tabs>
        </div>
    );
};

export default MonitoringDashboard;
