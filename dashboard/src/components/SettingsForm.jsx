import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription, CardFooter } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Eye, EyeOff } from 'lucide-react';

const SettingsForm = () => {
    const [settings, setSettings] = useState({});
    const [loading, setLoading] = useState(true);
    const [message, setMessage] = useState(null);
    const [visibleFields, setVisibleFields] = useState({});

    const fetchSettings = async () => {
        try {
            const response = await fetch('/dashboard/api/settings/');
            if (response.ok) {
                const data = await response.json();
                // Convert array to object for easier form handling
                const settingsMap = {};
                data.forEach(s => settingsMap[s.key] = s.value);
                setSettings(settingsMap);
            }
        } catch (error) {
            console.error("Failed to fetch settings:", error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchSettings();
    }, []);

    const handleSave = async (key, value) => {
        try {
            const response = await fetch('/dashboard/api/settings/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ key, value }),
            });
            if (response.ok) {
                setMessage(`Saved ${key}`);
                setTimeout(() => setMessage(null), 3000);
            }
        } catch (error) {
            console.error(`Failed to save ${key}:`, error);
        }
    };

    const handleChange = (key, value) => {
        setSettings(prev => ({ ...prev, [key]: value }));
    };

    const toggleVisibility = (key) => {
        setVisibleFields(prev => ({ ...prev, [key]: !prev[key] }));
    };

    const fields = [
        { key: 'casepeer_username', label: 'CasePeer Username', type: 'text' },
        { key: 'casepeer_password', label: 'CasePeer Password', type: 'password' },
        { key: 'casepeer_base_url', label: 'CasePeer Base URL', type: 'text' },
        { key: 'gmail_email', label: 'Gmail Email (for OTP)', type: 'email' },
        { key: 'gmail_app_password', label: 'Gmail App Password', type: 'password' },
        { key: 'otp_retry_count', label: 'OTP Retry Count', type: 'number' },
        { key: 'otp_retry_delay', label: 'OTP Retry Delay (seconds)', type: 'number' },
        { key: 'openai_api_key', label: 'OpenAI API Key', type: 'password' },
        { key: 'n8n_api_key', label: 'n8n API Key', type: 'password' },
        { key: 'n8n_webhook_url', label: 'n8n Webhook/Base URL', type: 'text' },
    ];

    return (
        <div className="space-y-6 max-w-2xl">
            <div className="flex justify-between items-center">
                <h2 className="text-3xl font-bold tracking-tight">Settings</h2>
            </div>

            <Card>
                <CardHeader>
                    <CardTitle>Application Configuration</CardTitle>
                    <CardDescription>Manage your API credentials and application settings.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    {fields.map((field) => (
                        <div key={field.key} className="grid w-full items-center gap-1.5">
                            <Label htmlFor={field.key}>{field.label}</Label>
                            <div className="flex gap-2">
                                <div className="relative flex-1">
                                    <Input
                                        type={field.type === 'password' && visibleFields[field.key] ? 'text' : field.type}
                                        id={field.key}
                                        value={settings[field.key] || ''}
                                        onChange={(e) => handleChange(field.key, e.target.value)}
                                        className={field.type === 'password' ? 'pr-10' : ''}
                                    />
                                    {field.type === 'password' && (
                                        <button
                                            type="button"
                                            className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                                            onClick={() => toggleVisibility(field.key)}
                                        >
                                            {visibleFields[field.key] ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                                        </button>
                                    )}
                                </div>
                                <Button variant="outline" onClick={() => handleSave(field.key, settings[field.key])}>
                                    Save
                                </Button>
                            </div>
                        </div>
                    ))}
                </CardContent>
                <CardFooter>
                    {message && <p className="text-sm text-green-600">{message}</p>}
                </CardFooter>
            </Card>
        </div>
    );
};

export default SettingsForm;
