import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar } from 'recharts';

const CostDashboard = () => {
    const [tokenUsage, setTokenUsage] = useState([]);
    const [openAiStats, setOpenAiStats] = useState(null);
    const [n8nStats, setN8nStats] = useState(null);
    const [loading, setLoading] = useState(true);

    const fetchData = async () => {
        setLoading(true);
        try {
            // Internal Token Usage
            const usageRes = await fetch('/internal-api/token_usage');
            if (usageRes.ok) {
                const data = await usageRes.json();
                setTokenUsage(data.map(item => ({
                    ...item,
                    dateStr: new Date(item.date).toLocaleDateString()
                })));
            }

            // OpenAI Stats
            const openaiRes = await fetch('/internal-api/integrations/openai/usage');
            if (openaiRes.ok) {
                setOpenAiStats(await openaiRes.json());
            }

            // n8n Stats
            const n8nRes = await fetch('/internal-api/integrations/n8n/executions');
            if (n8nRes.ok) {
                setN8nStats(await n8nRes.json());
            }

        } catch (error) {
            console.error("Failed to fetch dashboard data:", error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchData();
    }, []);

    const totalInternalCost = tokenUsage.reduce((acc, curr) => acc + curr.cost, 0);

    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center">
                <h2 className="text-3xl font-bold tracking-tight">System Costs & Usage</h2>
            </div>

            <Tabs defaultValue="overview" className="space-y-4">
                <TabsList>
                    <TabsTrigger value="overview">Overview</TabsTrigger>
                    <TabsTrigger value="openai">OpenAI Live</TabsTrigger>
                    <TabsTrigger value="n8n">n8n Executions</TabsTrigger>
                </TabsList>

                <TabsContent value="overview" className="space-y-4">
                    <div className="grid gap-4 md:grid-cols-2">
                        <Card>
                            <CardHeader><CardTitle>Total Recorded cost</CardTitle></CardHeader>
                            <CardContent>
                                <div className="text-4xl font-bold">${totalInternalCost.toFixed(4)}</div>
                                <p className="text-xs text-muted-foreground mt-1">Based on local logs</p>
                            </CardContent>
                        </Card>
                    </div>
                    <Card>
                        <CardHeader><CardTitle>Daily Trend</CardTitle></CardHeader>
                        <CardContent>
                            <div className="h-[300px] w-full">
                                <ResponsiveContainer width="100%" height="100%">
                                    <LineChart data={tokenUsage}>
                                        <CartesianGrid strokeDasharray="3 3" />
                                        <XAxis dataKey="dateStr" />
                                        <YAxis />
                                        <Tooltip />
                                        <Line type="monotone" dataKey="cost" stroke="#8884d8" />
                                    </LineChart>
                                </ResponsiveContainer>
                            </div>
                        </CardContent>
                    </Card>
                </TabsContent>

                <TabsContent value="openai" className="space-y-4">
                    <Card>
                        <CardHeader>
                            <CardTitle>OpenAI Usage</CardTitle>
                            <CardDescription>Live data fetched from OpenAI (Admin/Org Key required for full stats)</CardDescription>
                        </CardHeader>
                        <CardContent>
                            <pre className="bg-muted p-4 rounded-md overflow-auto max-h-[400px]">
                                {openAiStats ? JSON.stringify(openAiStats, null, 2) : "Loading or No Data..."}
                            </pre>
                        </CardContent>
                    </Card>
                </TabsContent>

                <TabsContent value="n8n" className="space-y-4">
                    <Card>
                        <CardHeader>
                            <CardTitle>n8n Workflow Executions</CardTitle>
                            <CardDescription>Recent execution activity</CardDescription>
                        </CardHeader>
                        <CardContent>
                            {n8nStats ? (
                                <div className="space-y-4">
                                    <div className="grid grid-cols-3 gap-4">
                                        <div className="p-4 border rounded-lg bg-green-50">
                                            <div className="text-sm font-medium text-green-800">Success</div>
                                            <div className="text-2xl font-bold text-green-600">{n8nStats.success}</div>
                                        </div>
                                        <div className="p-4 border rounded-lg bg-red-50">
                                            <div className="text-sm font-medium text-red-800">Errors</div>
                                            <div className="text-2xl font-bold text-red-600">{n8nStats.error}</div>
                                        </div>
                                        <div className="p-4 border rounded-lg">
                                            <div className="text-sm font-medium text-gray-800">Total Fetched</div>
                                            <div className="text-2xl font-bold">{n8nStats.total_fetched}</div>
                                        </div>
                                    </div>
                                    <div className="border rounded-md">
                                        <div className="p-3 bg-muted font-medium">Recent Executions</div>
                                        {n8nStats.recent_executions?.map((exec, i) => (
                                            <div key={i} className="p-3 border-t flex justify-between items-center text-sm">
                                                <span>{exec.id}</span>
                                                <span className={exec.finished ? "text-green-600" : "text-red-600"}>
                                                    {exec.finished ? "Success" : "Failed/Running"}
                                                </span>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            ) : (
                                <div>Loading or Key/URL not set in Settings...</div>
                            )}
                        </CardContent>
                    </Card>
                </TabsContent>
            </Tabs>
        </div>
    );
};

export default CostDashboard;
