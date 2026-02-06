import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CheckCircle, XCircle, Clock } from 'lucide-react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from 'recharts';

const N8nHealth = ({ executions = [], loading }) => {
    if (loading) return <div>Loading automation stats...</div>;

    const successful = executions.filter(e => e.finished && !e.stoppedAt).length; // Assuming 'stoppedAt' implies error or manual stop if check failed, but usually we check 'data.resultData.error'
    // Simplified logic: usually n8n execution object has 'finished' and 'mode'. 
    // We'll trust the parent to pass processed data or use simple checks.
    // Real n8n API response for executions usually has `finished`, `mode`, `startedAt`, `stoppedAt`.
    // If it failed, it might not have specific error flag at top level depending on version.
    // Let's assume we get a standard list.

    const errors = executions.filter(e => !e.finished || e.data?.resultData?.error).length;
    // Adjusting logic: logic depends on actual n8n response structure. 
    // For now we'll do: Success = finished=true, Error = everything else or explicit error.

    // Let's rely on a simpler prop structure passed from parent for safety, 
    // OR just visualizes what we have.
    // We will assume executions have { id, startedAt, finished, mode, retryOf }

    const total = executions.length;
    const successCount = executions.filter(e => e.finished).length;
    const errorCount = total - successCount;

    const data = [
        { name: 'Success', value: successCount, color: '#22c55e' }, // green-500
        { name: 'Error', value: errorCount, color: '#ef4444' },   // red-500
    ];

    return (
        <Card className="col-span-4 lg:col-span-2">
            <CardHeader>
                <CardTitle className="flex items-center gap-2">
                    <Clock className="h-5 w-5" />
                    Automation Health (n8n)
                </CardTitle>
            </CardHeader>
            <CardContent className="flex flex-row items-center justify-around">
                <div className="h-[200px] w-[200px]">
                    <ResponsiveContainer width="100%" height="100%">
                        <PieChart>
                            <Pie
                                data={data}
                                innerRadius={60}
                                outerRadius={80}
                                paddingAngle={5}
                                dataKey="value"
                            >
                                {data.map((entry, index) => (
                                    <Cell key={`cell-${index}`} fill={entry.color} />
                                ))}
                            </Pie>
                            <Tooltip />
                            <Legend />
                        </PieChart>
                    </ResponsiveContainer>
                </div>
                <div className="space-y-4">
                    <div className="flex items-center gap-2">
                        <CheckCircle className="h-4 w-4 text-green-500" />
                        <span className="font-medium">{successCount} Successful</span>
                    </div>
                    <div className="flex items-center gap-2">
                        <XCircle className="h-4 w-4 text-red-500" />
                        <span className="font-medium">{errorCount} Failed</span>
                    </div>
                    <div className="text-sm text-muted-foreground pt-2">
                        Last {total} executions
                    </div>
                </div>
            </CardContent>
        </Card>
    );
};

export default N8nHealth;
