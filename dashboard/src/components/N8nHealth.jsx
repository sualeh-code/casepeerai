import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CheckCircle, XCircle, Clock } from 'lucide-react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from 'recharts';

const N8nHealth = ({ executions = [], loading }) => {
    if (loading) return <div>Loading automation stats...</div>;

    // The original logic for filtering successful/error executions from an array
    // is commented out as the new logic will handle both array and object structures.
    // const successful = executions.filter(e => e.finished && !e.stoppedAt).length;
    // const errors = executions.filter(e => !e.finished || e.data?.resultData?.error).length;

    let successCount = 0;
    let errorCount = 0;
    let total = 0;

    if (executions && !Array.isArray(executions)) {
        // Handle summary object
        successCount = executions.success || 0;
        errorCount = executions.error || 0;
        total = executions.total_fetched || (successCount + errorCount);
    } else {
        // Handle array
        total = executions.length;
        successCount = executions.filter(e => e.finished).length;
        errorCount = total - successCount;
    }

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
