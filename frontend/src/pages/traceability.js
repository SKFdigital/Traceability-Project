import React, { useState } from 'react';
import axios from 'axios';

const Traceability = () => {
    const [loading, setLoading] = useState(false);
    const [message, setMessage] = useState('');

    const handleSync = async () => {
        setLoading(true);
        try {
            // Adjust the URL to match your backend host
            const response = await axios.post('http://localhost:8000/run_traceability_sync');
            setMessage('Sync successful: ' + response.data.message);
        } catch (error) {
            setMessage('Error running sync: ' + error.message);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="p-6">
            <h1 className="text-2xl font-bold">Traceability Dashboard</h1>
            <button 
                onClick={handleSync} 
                disabled={loading}
                className="mt-4 px-4 py-2 bg-blue-600 text-white rounded"
            >
                {loading ? 'Syncing...' : 'Run Traceability Sync'}
            </button>
            {message && <p className="mt-4">{message}</p>}
        </div>
    );
};

export default Traceability;
