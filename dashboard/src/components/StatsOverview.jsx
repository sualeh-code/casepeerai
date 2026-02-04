import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DollarSign, FileText, Mail, TrendingUp, Activity } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

const StatsOverview = () => {
    const [stats, setStats] = useState({
        totalCases: 0,
        activeCases: 0,
        totalRevenue: 0,
        totalSavings: 0,
        totalEmails: 0
    });
    const [chartData, setChartData] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchStats = async () => {
            try {
                const response = await fetch('/api/cases');
                if (response.ok) {
                    const data = await response.json();

                    const totalCases = data.length;
                    const activeCases = data.filter(c => c.status === 'Active').length;
                    const totalRevenue = data.reduce((acc, curr) => acc + (curr.revenue || 0), 0);
                    const totalSavings = data.reduce((acc, curr) => acc + (curr.savings || 0), 0);
                    const totalEmails = data.reduce((acc, curr) => acc + (curr.emails_received || 0) + (curr.emails_sent || 0), 0);

                    // Format data for chart
                    const chartData = data.map(c => ({
                        name: c.case_name.substring(0, 10) + (c.case_name.length > 10 ? '...' : ''),
                        revenue: c.revenue || 0
                    }));

                    setStats({
                        totalCases,
                        activeCases,
                        totalRevenue,
                        totalSavings,
                        totalEmails
                    });
                    setChartData(chartData);
                }
            } catch (error) {
                console.error("Failed to fetch stats:", error);
            } finally {
                setLoading(false);
            }
        };

        fetchStats();
    }, []);

    const cards = [
        {
            title: "Total Revenue",
            value: `$${stats.totalRevenue.toLocaleString()}`,
            icon: DollarSign,
            description: "Total revenue across all cases",
            color: "text-green-500"
        },
        {
            title: "Potential Savings",
            value: `$${stats.totalSavings.toLocaleString()}`,
            icon: TrendingUp,
            description: "Total calculated savings",
            color: "text-blue-500"
        },
        {
            title: "Active Cases",
            value: stats.activeCases,
            icon: Activity,
            description: `${stats.totalCases} total cases tracked`,
            color: "text-purple-500"
        },
        {
            title: "Emails Processed",
            value: stats.totalEmails,
            icon: Mail,
            description: "Inbound and outbound emails",
            color: "text-orange-500"
        }
    ];

    if (loading) {
        return <div className="p-8 text-center text-muted-foreground">Loading dashboard stats...</div>;
    }

    return (
        <div className="space-y-6">
            <h2 className="text-3xl font-bold tracking-tight">Dashboard Overview</h2>

            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                {cards.map((card, index) => (
                    <Card key={index}>
                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                            <CardTitle className="text-sm font-medium">
                                {card.title}
                            </CardTitle>
                            <card.icon className={`h-4 w-4 ${card.color}`} />
                        </CardHeader>
                        <CardContent>
                            <div className="text-2xl font-bold">{card.value}</div>
                            <p className="text-xs text-muted-foreground mt-1">
                                {card.description}
                            </p>
                        </CardContent>
                    </Card>
                ))}
            </div>

            {/* Revenue Chart */}
            <Card className="col-span-4">
                <CardHeader>
                    <CardTitle>Revenue per Case</CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="h-[300px] w-full">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={chartData}>
                                <CartesianGrid strokeDasharray="3 3" />
                                <XAxis dataKey="name" />
                                <YAxis />
                                <Tooltip
                                    formatter={(value) => [`$${value}`, 'Revenue']}
                                    contentStyle={{ backgroundColor: 'hsl(var(--card))', borderColor: 'hsl(var(--border))', color: 'hsl(var(--foreground))' }}
                                />
                                <Bar dataKey="revenue" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} />
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </CardContent>
            </Card>
        </div>
    );
};

export default StatsOverview;
