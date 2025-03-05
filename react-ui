import React, { useState, useEffect } from 'react';
import { Card, CardHeader, CardContent, CardFooter } from '@/components/ui/card';

const OVMSCommandTerminal = () => {
  const [vehicleId, setVehicleId] = useState('');
  const [command, setCommand] = useState('');
  const [params, setParams] = useState('');
  const [response, setResponse] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [history, setHistory] = useState([]);
  const [vehicles, setVehicles] = useState([]);
  const [commonCommands, setCommonCommands] = useState([
    { name: 'stat', description: 'Vehicle status' },
    { name: 'charge status', description: 'Charging status' },
    { name: 'charge start', description: 'Start charging' },
    { name: 'charge stop', description: 'Stop charging' },
    { name: 'climate status', description: 'Climate status' },
    { name: 'lock', description: 'Lock vehicle' },
    { name: 'unlock', description: 'Unlock vehicle' },
    { name: 'metrics list', description: 'List metrics' },
    { name: 'wakeup', description: 'Wake up vehicle' },
  ]);

  useEffect(() => {
    // This would fetch available vehicles from HA
    async function fetchVehicles() {
      try {
        // This is a placeholder - would need to use HA websocket API
        const result = await fetchHassEntities('ovms');
        setVehicles(result || []);
      } catch (error) {
        console.error('Error fetching vehicles:', error);
      }
    }
    
    fetchVehicles();
  }, []);

  const sendCommand = async () => {
    if (!vehicleId || !command) return;
    
    setIsLoading(true);
    
    try {
      // Call Home Assistant service
      const result = await callService('ovms', 'send_command', {
        vehicle_id: vehicleId,
        command: command,
        parameters: params
      });
      
      // Process response
      const cmdText = params ? `${command} ${params}` : command;
      const newHistoryItem = {
        command: cmdText,
        response: result.response || 'No response',
        timestamp: new Date().toLocaleTimeString()
      };
      
      setResponse(result.response || 'Command sent successfully');
      setHistory([newHistoryItem, ...history.slice(0, 9)]); // Keep last 10 items
    } catch (error) {
      setResponse(`Error: ${error.message || 'Unknown error'}`);
    } finally {
      setIsLoading(false);
    }
  };
  
  const handleCommandSelect = (cmd) => {
    // When selecting from common commands
    const parts = cmd.name.split(' ');
    if (parts.length > 1) {
      setCommand(parts[0]);
      setParams(parts.slice(1).join(' '));
    } else {
      setCommand(cmd.name);
      setParams('');
    }
  };

  return (
    <Card className="w-full">
      <CardHeader>
        <h2 className="text-xl font-bold">OVMS Command Terminal</h2>
      </CardHeader>
      <CardContent>
        {/* Vehicle Selection */}
        <div className="mb-4">
          <label className="block text-sm font-medium mb-1">Vehicle</label>
          <select 
            value={vehicleId} 
            onChange={(e) => setVehicleId(e.target.value)}
            className="w-full p-2 border rounded"
          >
            <option value="">Select vehicle</option>
            {vehicles.map(v => (
              <option key={v.id} value={v.id}>{v.name}</option>
            ))}
          </select>
        </div>
        
        {/* Command Input */}
        <div className="mb-4">
          <label className="block text-sm font-medium mb-1">Command</label>
          <div className="flex gap-2">
            <input 
              type="text" 
              value={command}
              onChange={(e) => setCommand(e.target.value)}
              className="flex-1 p-2 border rounded"
              placeholder="Enter command"
            />
            <select 
              className="p-2 border rounded"
              onChange={(e) => {
                const cmd = commonCommands.find(c => c.name === e.target.value);
                if (cmd) handleCommandSelect(cmd);
              }}
            >
              <option value="">Common commands</option>
              {commonCommands.map(cmd => (
                <option key={cmd.name} value={cmd.name}>
                  {cmd.name}
                </option>
              ))}
            </select>
          </div>
        </div>
        
        {/* Parameters Input */}
        <div className="mb-4">
          <label className="block text-sm font-medium mb-1">Parameters</label>
          <input 
            type="text" 
            value={params}
            onChange={(e) => setParams(e.target.value)}
            className="w-full p-2 border rounded"
            placeholder="Enter parameters (optional)"
          />
        </div>
        
        {/* Response Display */}
        <div className="mb-4">
          <label className="block text-sm font-medium mb-1">Response</label>
          <div className="w-full h-24 p-2 bg-gray-100 border rounded overflow-auto">
            {isLoading ? (
              <div className="flex justify-center items-center h-full">
                <span>Sending command...</span>
              </div>
            ) : (
              <pre className="whitespace-pre-wrap">{response}</pre>
            )}
          </div>
        </div>
        
        {/* Command History */}
        {history.length > 0 && (
          <div>
            <label className="block text-sm font-medium mb-1">Command History</label>
            <div className="max-h-48 overflow-y-auto">
              {history.map((item, index) => (
                <div key={index} className="mb-2 p-2 border-b">
                  <div className="flex justify-between">
                    <span className="font-medium">{item.command}</span>
                    <span className="text-xs text-gray-500">{item.timestamp}</span>
                  </div>
                  <pre className="text-sm whitespace-pre-wrap text-gray-600">{item.response}</pre>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
      <CardFooter>
        <button 
          onClick={sendCommand}
          disabled={isLoading || !vehicleId || !command}
          className="px-4 py-2 bg-blue-500 text-white rounded disabled:bg-blue-300"
        >
          Send Command
        </button>
      </CardFooter>
    </Card>
  );
};

// Placeholder for Home Assistant API calls
function fetchHassEntities() {
  // In real implementation, this would use the HA WebSocket API
  return Promise.resolve([
    { id: 'my_ovms', name: 'My EV' },
    { id: 'other_vehicle', name: 'Second Vehicle' }
  ]);
}

function callService(domain, service, data) {
  // In real implementation, this would call the HA service
  console.log(`Calling ${domain}.${service} with:`, data);
  return Promise.resolve({
    success: true,
    response: `Simulated response for ${data.command}`
  });
}

export default OVMSCommandTerminal;
