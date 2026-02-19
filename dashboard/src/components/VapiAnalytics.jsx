import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend } from 'recharts';

const COLORS = ['#8b5cf6', '#06b6d4', '#10b981', '#f59e0b', '#ef4444', '#6366f1', '#ec4899', '#14b8a6'];

const VapiAnalytics = () => {
    const [callData, setCallData] = useState(null);
    const [analytics, setAnalytics] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        const fetchData = async () => {
            try {
                const [callsRes, analyticsRes] = await Promise.all([
                    fetch('/internal-api/integrations/vapi/calls'),
                    fetch('/internal-api/integrations/vapi/analytics', { method: 'POST' })
                ]);

                if (callsRes.ok) {
                    const data = await callsRes.json();
                    if (data.error) {
                        setError(data.error);
                    } else {
                        setCallData(data);
                    }
                } else if (callsRes.status === 400) {
                    setError("VAPI API Key not configured. Go to Settings to add it.");
                } else {
                    setError("Failed to fetch VAPI data");
                }

                if (analyticsRes.ok) {
                    setAnalytics(await analyticsRes.json());
                }
            } catch (err) {
                console.error("Failed to fetch VAPI data:", err);
                setError("Failed to connect to VAPI API");
            } finally {
                setLoading(false);
            }
        };
        fetchData();
    }, []);

    if (loading) return <div className="p-8 text-muted-foreground">Loading VAPI data...</div>;

    if (error) {
        return (
            <div className="space-y-6">
                <h2 className="text-3xl font-bold tracking-tight">VAPI Analytics</h2>
                <Card>
                    <CardContent className="p-6">
                        <div className="text-muted-foreground">{error}</div>
                    </CardContent>
                </Card>
            </div>
        );
    }

    // Prepare chart data
    const statusData = callData?.status_breakdown
        ? Object.entries(callData.status_breakdown).map(([name, value]) => ({ name, value }))
        : [];

    const typeData = callData?.type_breakdown
        ? Object.entries(callData.type_breakdown).map(([name, value]) => ({ name: formatLabel(name), value }))
        : [];

    const endReasonData = callData?.end_reasons
        ? Object.entries(callData.end_reasons)
            .sort((a, b) => b[1] - a[1])
            .slice(0, 8)
            .map(([name, value]) => ({ name: formatLabel(name), value }))
        : [];

    // Cost per call for recent calls
    const recentCostData = callData?.recent_calls
        ? callData.recent_calls
            .filter(c => c.cost > 0)
            .map(c => ({
                name: c.id.substring(0, 8),
                cost: parseFloat((c.cost || 0).toFixed(4)),
                duration: Math.round((c.duration || 0) / 60 * 10) / 10,
            }))
        : [];

    return (
        <div className="space-y-6">
            <h2 className="text-3xl font-bold tracking-tight">VAPI Analytics</h2>

            {/* KPI Cards */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Total Calls</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{callData?.total_calls || 0}</div>
                        <p className="text-xs text-muted-foreground">
                            {callData?.in_progress_count || 0} in progress
                        </p>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Total Cost</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">${callData?.total_cost?.toFixed(2) || '0.00'}</div>
                        <p className="text-xs text-muted-foreground">
                            ${callData?.avg_cost_per_call?.toFixed(4) || '0'} avg per call
                        </p>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Total Duration</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{callData?.total_duration_minutes?.toFixed(1) || 0} min</div>
                        <p className="text-xs text-muted-foreground">
                            {callData?.avg_duration_seconds?.toFixed(0) || 0}s avg per call
                        </p>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Cost/Minute</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">
                            ${callData?.total_duration_minutes > 0
                                ? (callData.total_cost / callData.total_duration_minutes).toFixed(4)
                                : '0.00'}
                        </div>
                        <p className="text-xs text-muted-foreground">Average rate</p>
                    </CardContent>
                </Card>
            </div>

            {/* Charts Row 1 */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-7">
                {/* Cost per Call Bar Chart */}
                <Card className="col-span-4">
                    <CardHeader>
                        <CardTitle>Cost per Call (Recent)</CardTitle>
                        <CardDescription>Cost in USD for the most recent calls</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="h-[300px] w-full">
                            {recentCostData.length > 0 ? (
                                <ResponsiveContainer width="100%" height="100%">
                                    <BarChart data={recentCostData}>
                                        <CartesianGrid strokeDasharray="3 3" />
                                        <XAxis dataKey="name" />
                                        <YAxis />
                                        <Tooltip
                                            contentStyle={{ backgroundColor: 'hsl(var(--card))' }}
                                            formatter={(value, name) => [
                                                name === 'cost' ? `$${value}` : `${value} min`,
                                                name === 'cost' ? 'Cost' : 'Duration'
                                            ]}
                                        />
                                        <Legend />
                                        <Bar dataKey="cost" fill="#8b5cf6" name="Cost ($)" />
                                    </BarChart>
                                </ResponsiveContainer>
                            ) : (
                                <div className="h-full flex items-center justify-center text-muted-foreground">No cost data available</div>
                            )}
                        </div>
                    </CardContent>
                </Card>

                {/* Call Type Distribution Pie */}
                <Card className="col-span-3">
                    <CardHeader>
                        <CardTitle>Call Types</CardTitle>
                        <CardDescription>Distribution by call type</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="h-[300px] w-full">
                            {typeData.length > 0 ? (
                                <ResponsiveContainer width="100%" height="100%">
                                    <PieChart>
                                        <Pie
                                            data={typeData}
                                            cx="50%"
                                            cy="50%"
                                            innerRadius={60}
                                            outerRadius={80}
                                            paddingAngle={5}
                                            dataKey="value"
                                        >
                                            {typeData.map((_, index) => (
                                                <Cell key={'cell-' + index} fill={COLORS[index % COLORS.length]} />
                                            ))}
                                        </Pie>
                                        <Tooltip />
                                        <Legend />
                                    </PieChart>
                                </ResponsiveContainer>
                            ) : (
                                <div className="h-full flex items-center justify-center text-muted-foreground">No type data</div>
                            )}
                        </div>
                    </CardContent>
                </Card>
            </div>

            {/* Charts Row 2 */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-7">
                {/* End Reasons Bar Chart */}
                <Card className="col-span-4">
                    <CardHeader>
                        <CardTitle>Call End Reasons</CardTitle>
                        <CardDescription>Why calls ended (top 8)</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="h-[300px] w-full">
                            {endReasonData.length > 0 ? (
                                <ResponsiveContainer width="100%" height="100%">
                                    <BarChart data={endReasonData} layout="vertical">
                                        <CartesianGrid strokeDasharray="3 3" />
                                        <XAxis type="number" />
                                        <YAxis dataKey="name" type="category" width={120} tick={{ fontSize: 11 }} />
                                        <Tooltip contentStyle={{ backgroundColor: 'hsl(var(--card))' }} />
                                        <Bar dataKey="value" fill="#06b6d4" name="Count" />
                                    </BarChart>
                                </ResponsiveContainer>
                            ) : (
                                <div className="h-full flex items-center justify-center text-muted-foreground">No end reason data</div>
                            )}
                        </div>
                    </CardContent>
                </Card>

                {/* Status Distribution */}
                <Card className="col-span-3">
                    <CardHeader>
                        <CardTitle>Call Status</CardTitle>
                        <CardDescription>Current status distribution</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="h-[300px] w-full">
                            {statusData.length > 0 ? (
                                <ResponsiveContainer width="100%" height="100%">
                                    <PieChart>
                                        <Pie
                                            data={statusData}
                                            cx="50%"
                                            cy="50%"
                                            innerRadius={60}
                                            outerRadius={80}
                                            paddingAngle={5}
                                            dataKey="value"
                                        >
                                            {statusData.map((_, index) => (
                                                <Cell key={'cell-' + index} fill={COLORS[index % COLORS.length]} />
                                            ))}
                                        </Pie>
                                        <Tooltip />
                                        <Legend />
                                    </PieChart>
                                </ResponsiveContainer>
                            ) : (
                                <div className="h-full flex items-center justify-center text-muted-foreground">No status data</div>
                            )}
                        </div>
                    </CardContent>
                </Card>
            </div>

            {/* Recent Calls Table */}
            <Card>
                <CardHeader>
                    <CardTitle>Recent Calls</CardTitle>
                    <CardDescription>Last 20 VAPI calls</CardDescription>
                </CardHeader>
                <CardContent>
                    <div className="border rounded-md overflow-auto">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="bg-muted">
                                    <th className="p-3 text-left font-medium">ID</th>
                                    <th className="p-3 text-left font-medium">Type</th>
                                    <th className="p-3 text-left font-medium">Status</th>
                                    <th className="p-3 text-right font-medium">Cost</th>
                                    <th className="p-3 text-right font-medium">Duration</th>
                                    <th className="p-3 text-left font-medium">End Reason</th>
                                    <th className="p-3 text-left font-medium">Started</th>
                                </tr>
                            </thead>
                            <tbody>
                                {callData?.recent_calls?.length > 0 ? (
                                    callData.recent_calls.map((call) => (
                                        <tr key={call.id} className="border-t hover:bg-muted/50">
                                            <td className="p-3 font-mono text-xs">{call.id.substring(0, 12)}...</td>
                                            <td className="p-3">{formatLabel(call.type)}</td>
                                            <td className="p-3">
                                                <span className={
                                                    call.status === 'ended' ? 'text-green-600 font-medium' :
                                                    call.status === 'in-progress' ? 'text-blue-600 font-medium' :
                                                    'text-muted-foreground'
                                                }>
                                                    {call.status}
                                                </span>
                                            </td>
                                            <td className="p-3 text-right font-mono">${(call.cost || 0).toFixed(4)}</td>
                                            <td className="p-3 text-right">{call.duration ? `${Math.round(call.duration)}s` : '-'}</td>
                                            <td className="p-3 text-xs">{formatLabel(call.endedReason || '-')}</td>
                                            <td className="p-3 text-xs text-muted-foreground">
                                                {call.startedAt ? new Date(call.startedAt).toLocaleString() : '-'}
                                            </td>
                                        </tr>
                                    ))
                                ) : (
                                    <tr><td colSpan={7} className="p-4 text-center text-muted-foreground">No calls found</td></tr>
                                )}
                            </tbody>
                        </table>
                    </div>
                </CardContent>
            </Card>

            {/* Cost Breakdown from individual calls */}
            {callData?.recent_calls?.some(c => c.costBreakdown && Object.keys(c.costBreakdown).length > 0) && (
                <Card>
                    <CardHeader>
                        <CardTitle>Cost Breakdown (Latest Call)</CardTitle>
                        <CardDescription>Detailed cost components from the most recent call</CardDescription>
                    </CardHeader>
                    <CardContent>
                        {(() => {
                            const latestWithCost = callData.recent_calls.find(c => c.costBreakdown && Object.keys(c.costBreakdown).length > 0);
                            if (!latestWithCost) return <div className="text-muted-foreground">No breakdown available</div>;
                            const breakdown = latestWithCost.costBreakdown;
                            // Only show top-level numeric fields (skip nested objects like analysisCostBreakdown)
                            const numericEntries = Object.entries(breakdown).filter(([, v]) => typeof v === 'number');
                            return (
                                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                                    {numericEntries.map(([key, value]) => (
                                        <div key={key} className="p-3 border rounded-lg">
                                            <div className="text-xs font-medium text-muted-foreground capitalize">{formatLabel(key)}</div>
                                            <div className="text-lg font-bold">
                                                {key.includes('Token') || key.includes('Characters')
                                                    ? value.toLocaleString()
                                                    : `$${value.toFixed(4)}`}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            );
                        })()}
                    </CardContent>
                </Card>
            )}
        </div>
    );
};

function formatLabel(str) {
    if (!str || str === '-') return str;
    return str
        .replace(/([A-Z])/g, ' $1')
        .replace(/[-_]/g, ' ')
        .replace(/\b\w/g, l => l.toUpperCase())
        .trim();
}

export default VapiAnalytics;
