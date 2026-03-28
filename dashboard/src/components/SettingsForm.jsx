import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription, CardFooter } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Eye, EyeOff } from 'lucide-react';

// Known fields with friendly labels and types
const KNOWN_FIELDS = {
    casepeer_username: { label: 'CasePeer Username', type: 'text' },
    casepeer_password: { label: 'CasePeer Password', type: 'password' },
    casepeer_base_url: { label: 'CasePeer Base URL', type: 'text' },
    gmail_email: { label: 'Gmail Email (for OTP)', type: 'email' },
    gmail_app_password: { label: 'Gmail App Password', type: 'password' },
    otp_retry_count: { label: 'OTP Retry Count', type: 'number' },
    otp_retry_delay: { label: 'OTP Retry Delay (seconds)', type: 'number' },
    openai_api_key: { label: 'OpenAI API Key', type: 'password' },
    gemini_api_key: { label: 'Gemini API Key (PDF analysis)', type: 'password' },
    n8n_api_key: { label: 'n8n API Key', type: 'password' },
    n8n_webhook_url: { label: 'n8n Webhook/Base URL', type: 'text' },
    vapi_api_key: { label: 'VAPI API Key', type: 'password' },
    vapi_assistant_id: { label: 'VAPI Assistant ID', type: 'text' },
    vapi_phone_id: { label: 'VAPI Phone Number ID', type: 'text' },
    provider_calls_enabled: { label: 'Provider Calls Enabled', type: 'text' },
    auto_provider_calls_enabled: { label: 'Auto-Call on New Case', type: 'text' },
    provider_calls_max_attempts: { label: 'Max Call Attempts per Provider', type: 'number' },
    notification_email: { label: 'Notification Email (call alerts)', type: 'email' },
    debug_override_phone: { label: 'Debug Override Phone (all calls dial this #)', type: 'text' },
    gmail_signature: { label: 'Gmail Signature (HTML)', type: 'text' },
    gmail_oauth2_refresh_token: { label: 'Gmail OAuth2 Refresh Token', type: 'password' },
    gmail_oauth2_client_id: { label: 'Gmail OAuth2 Client ID', type: 'text' },
    gmail_oauth2_client_secret: { label: 'Gmail OAuth2 Client Secret', type: 'password' },
    escalation_email: { label: 'Escalation Email', type: 'email' },
    neg0sub_recipient_override: { label: 'Neg0sub Recipient Override', type: 'email' },
};

function guessFieldType(key) {
    if (key.includes('password') || key.includes('secret') || key.includes('token') || key.includes('api_key')) return 'password';
    if (key.includes('email')) return 'email';
    if (key.includes('count') || key.includes('delay') || key.includes('retry')) return 'number';
    return 'text';
}

function formatLabel(key) {
    return key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

const SettingsForm = () => {
    const [settings, setSettings] = useState({});
    const [loading, setLoading] = useState(true);
    const [message, setMessage] = useState(null);
    const [visibleFields, setVisibleFields] = useState({});
    const [fields, setFields] = useState([]);

    const fetchSettings = async () => {
        try {
            const response = await fetch('/internal-api/settings');
            if (response.ok) {
                const data = await response.json();
                const settingsMap = {};
                data.forEach(s => settingsMap[s.key] = s.value);
                setSettings(settingsMap);

                // Known fields first (in defined order), then any extra keys from Turso
                const knownKeys = Object.keys(KNOWN_FIELDS);
                const allKeys = data.map(s => s.key);
                const extraKeys = allKeys.filter(k => !KNOWN_FIELDS[k]);

                const fieldList = [
                    ...knownKeys.map(key => ({
                        key,
                        label: KNOWN_FIELDS[key].label,
                        type: KNOWN_FIELDS[key].type,
                    })),
                    ...extraKeys.map(key => ({
                        key,
                        label: formatLabel(key),
                        type: guessFieldType(key),
                    })),
                ];
                setFields(fieldList);
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
            const response = await fetch('/internal-api/settings', {
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

    return (
        <div className="space-y-6 max-w-2xl">
            <div className="flex justify-between items-center">
                <h2 className="text-3xl font-bold tracking-tight">Settings</h2>
            </div>

            <Card>
                <CardHeader>
                    <CardTitle>Application Configuration</CardTitle>
                    <CardDescription>Manage your API credentials and application settings. All fields from the database are shown below.</CardDescription>
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
