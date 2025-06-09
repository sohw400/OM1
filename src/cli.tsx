#!/usr/bin/env node
import React, { useState, useEffect } from 'react';
import { render, Box, Text, useInput, useApp } from 'ink';
import TextInput from 'ink-text-input';
import { readdir, readFile, writeFile, access } from 'fs/promises';
import { join } from 'path';
import { spawn, spawnSync } from 'child_process';
import * as dotenv from 'dotenv';

interface Config {
  name: string;
  path: string;
  content?: any;
}

interface AppProps {}

interface ApiKey {
  name: string;
  value: string;
  description: string;
}

const App: React.FC<AppProps> = () => {
  const [configs, setConfigs] = useState<Config[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [mode, setMode] = useState<'main' | 'select' | 'preview' | 'running' | 'apikeys' | 'editkey' | 'editconfig'>('main');
  const [configContent, setConfigContent] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [apiKeys, setApiKeys] = useState<ApiKey[]>([]);
  const [selectedKeyIndex, setSelectedKeyIndex] = useState(0);
  const [editingKey, setEditingKey] = useState<ApiKey | null>(null);
  const [keyInput, setKeyInput] = useState('');
  const [editingConfig, setEditingConfig] = useState<Config | null>(null);
  const [configInput, setConfigInput] = useState('');
  const { exit } = useApp();

  useEffect(() => {
    // Load environment variables
    dotenv.config();
    loadConfigs();
    loadApiKeys();
  }, []);

  const loadConfigs = async () => {
    try {
      const configDir = join(process.cwd(), 'config');
      const files = await readdir(configDir);
      const configFiles = files
        .filter(file => file.endsWith('.json5'))
        .map(file => ({
          name: file.replace('.json5', ''),
          path: join(configDir, file)
        }));
      
      setConfigs(configFiles);
      setLoading(false);
    } catch (error) {
      console.error('Error loading configs:', error);
      setLoading(false);
    }
  };

  const loadApiKeys = async () => {
    const defaultKeys: ApiKey[] = [
      { name: 'OM_API_KEY', value: process.env.OM_API_KEY || '', description: 'OpenMind API Key - Required for all LLM and VLM services' },
      { name: 'URID', value: process.env.URID || '', description: 'User Resource ID - Required for OpenMind services' },
      { name: 'ETH_ADDRESS', value: process.env.ETH_ADDRESS || '', description: 'Ethereum wallet address - Required for blockchain features' },
      { name: 'COINBASE_WALLET_ID', value: process.env.COINBASE_WALLET_ID || '', description: 'Coinbase wallet ID - Required for Coinbase integration' },
      { name: 'COINBASE_API_KEY', value: process.env.COINBASE_API_KEY || '', description: 'Coinbase API key - Required for Coinbase wallet operations' },
      { name: 'COINBASE_API_SECRET', value: process.env.COINBASE_API_SECRET || '', description: 'Coinbase API secret - Required for Coinbase wallet operations' },
      { name: 'TWITTER_API_KEY', value: process.env.TWITTER_API_KEY || '', description: 'Twitter API key - Required for Twitter integration' },
      { name: 'TWITTER_API_SECRET', value: process.env.TWITTER_API_SECRET || '', description: 'Twitter API secret - Required for Twitter integration' },
      { name: 'TWITTER_ACCESS_TOKEN', value: process.env.TWITTER_ACCESS_TOKEN || '', description: 'Twitter access token - Required for Twitter posting' },
      { name: 'TWITTER_ACCESS_TOKEN_SECRET', value: process.env.TWITTER_ACCESS_TOKEN_SECRET || '', description: 'Twitter access token secret - Required for Twitter posting' },
      { name: 'OPENAI_API_KEY', value: process.env.OPENAI_API_KEY || '', description: 'OpenAI API key - Required for direct OpenAI API usage' },
    ];
    setApiKeys(defaultKeys);
  };

  const saveApiKey = async (key: ApiKey) => {
    try {
      const envPath = join(process.cwd(), '.env');
      let envContent = '';
      
      try {
        envContent = await readFile(envPath, 'utf-8');
      } catch {
        // File doesn't exist, create new
      }

      const lines = envContent.split('\n');
      const keyIndex = lines.findIndex(line => line.startsWith(`${key.name}=`));
      
      if (keyIndex >= 0) {
        lines[keyIndex] = `${key.name}=${key.value}`;
      } else {
        lines.push(`${key.name}=${key.value}`);
      }

      await writeFile(envPath, lines.join('\n'));
      
      // Update environment variable
      process.env[key.name] = key.value;
      
      // Reload API keys
      loadApiKeys();
    } catch (error) {
      console.error('Error saving API key:', error);
    }
  };

  const loadConfigContent = async (config: Config) => {
    try {
      const content = await readFile(config.path, 'utf-8');
      setConfigContent(content);
    } catch (error) {
      setConfigContent('Error loading config content');
    }
  };

  const saveConfigContent = async (config: Config, content: string) => {
    try {
      // Validate JSON before saving
      JSON.parse(content);
      await writeFile(config.path, content);
      setConfigContent(content);
      return true;
    } catch (error) {
      console.error('Error saving config:', error);
      return false;
    }
  };

  const runConfig = (configName: string) => {
    setMode('running');
    const child = spawn('uv', ['run', 'src/run.py', configName], {
      stdio: 'inherit',
      cwd: process.cwd()
    });

    child.on('close', (code) => {
      exit();
    });
  };

  useInput((input: string, key: any) => {
    if (mode === 'main') {
      if (key.upArrow && selectedIndex > 0) {
        setSelectedIndex(selectedIndex - 1);
      } else if (key.downArrow && selectedIndex < 1) {
        setSelectedIndex(selectedIndex + 1);
      } else if (key.return) {
        if (selectedIndex === 0) {
          setMode('select');
          setSelectedIndex(0);
        } else {
          setMode('apikeys');
          setSelectedKeyIndex(0);
        }
      } else if (input === 'q') {
        exit();
      }
    } else if (mode === 'select') {
      if (key.upArrow && selectedIndex > 0) {
        setSelectedIndex(selectedIndex - 1);
      } else if (key.downArrow && selectedIndex < configs.length - 1) {
        setSelectedIndex(selectedIndex + 1);
      } else if (key.return) {
        const selectedConfig = configs[selectedIndex];
        loadConfigContent(selectedConfig);
        setMode('preview');
      } else if (key.escape || input === 'b') {
        setMode('main');
        setSelectedIndex(0);
      } else if (input === 'q') {
        exit();
      }
    } else if (mode === 'preview') {
      if (input === 'r') {
        const selectedConfig = configs[selectedIndex];
        runConfig(selectedConfig.name);
      } else if (input === 'e') {
        const selectedConfig = configs[selectedIndex];
        setEditingConfig(selectedConfig);
        setConfigInput(configContent);
        setMode('editconfig');
      } else if (key.escape || input === 'b') {
        setMode('select');
      } else if (input === 'q') {
        exit();
      }
    } else if (mode === 'apikeys') {
      if (key.upArrow && selectedKeyIndex > 0) {
        setSelectedKeyIndex(selectedKeyIndex - 1);
      } else if (key.downArrow && selectedKeyIndex < apiKeys.length - 1) {
        setSelectedKeyIndex(selectedKeyIndex + 1);
      } else if (key.return) {
        const selectedKey = apiKeys[selectedKeyIndex];
        setEditingKey(selectedKey);
        setKeyInput(selectedKey.value);
        setMode('editkey');
      } else if (key.escape || input === 'b') {
        setMode('main');
        setSelectedIndex(1);
      } else if (input === 'q') {
        exit();
      }
    } else if (mode === 'editkey') {
      if (key.escape) {
        setMode('apikeys');
        setEditingKey(null);
        setKeyInput('');
      }
    } else if (mode === 'editconfig') {
      if (key.escape || input === 'b') {
        setMode('preview');
        setEditingConfig(null);
        setConfigInput('');
      } else if (input === 'r') {
        // Reload the config file
        if (editingConfig) {
          const reloadConfig = async () => {
            try {
              const content = await readFile(editingConfig.path, 'utf-8');
              setConfigContent(content);
              setConfigInput(content);
            } catch (error) {
              console.error('Error reloading config:', error);
            }
          };
          reloadConfig();
        }
      } else if (input === 's') {
        // Save the current content
        if (editingConfig) {
          saveConfigContent(editingConfig, configInput);
        }
      } else if (input === 'o') {
        // Open in external editor
        if (editingConfig) {
          try {
            // Simple and reliable approach - just use open command on macOS
            spawn('open', ['-t', editingConfig.path], { 
              detached: true, 
              stdio: 'ignore' 
            });
          } catch (error) {
            console.error(`Could not open editor. File path: ${editingConfig.path}`);
            console.error(`You can manually edit the file and press 'r' to reload.`);
          }
        }
      }
    }
  });

  if (loading) {
    return (
      <Box>
        <Text>Loading configurations...</Text>
      </Box>
    );
  }

  if (mode === 'running') {
    return (
      <Box flexDirection="column">
        <Box marginBottom={1}>
          <Text color="green">Running configuration: {configs[selectedIndex]?.name}</Text>
        </Box>
        <Box>
          <Text color="gray">Press Ctrl+C to stop</Text>
        </Box>
      </Box>
    );
  }

  if (mode === 'preview') {
    const selectedConfig = configs[selectedIndex];
    return (
      <Box flexDirection="column">
        <Box marginBottom={1}>
          <Text color="cyan" bold>Configuration: {selectedConfig.name}</Text>
        </Box>
        <Box marginBottom={1}>
          <Text color="gray">Press 'r' to run, 'e' to edit, 'b' to go back, 'q' to quit</Text>
        </Box>
        <Box borderStyle="single" padding={1}>
          <Text>{configContent}</Text>
        </Box>
      </Box>
    );
  }

  if (mode === 'apikeys') {
    return (
      <Box flexDirection="column">
        <Box marginBottom={1}>
          <Text color="cyan" bold>API Keys Management</Text>
        </Box>
        <Box marginBottom={1}>
          <Text color="gray">Use ↑/↓ to navigate, Enter to edit, 'b' to go back, 'q' to quit</Text>
        </Box>
        <Box flexDirection="column">
          {apiKeys.map((key, index) => (
            <Box key={key.name} marginBottom={1}>
              <Text color={index === selectedKeyIndex ? 'green' : 'white'}>
                {index === selectedKeyIndex ? '► ' : '  '}
                <Text bold>{key.name}</Text>: {key.value ? '********' : 'Not set'}
              </Text>
              <Box marginLeft={4}>
                <Text color="gray">{key.description}</Text>
              </Box>
            </Box>
          ))}
        </Box>
      </Box>
    );
  }

  if (mode === 'editkey' && editingKey) {
    return (
      <Box flexDirection="column">
        <Box marginBottom={1}>
          <Text color="cyan" bold>Edit API Key: {editingKey.name}</Text>
        </Box>
        <Box marginBottom={1}>
          <Text color="gray">{editingKey.description}</Text>
        </Box>
        <Box marginBottom={1}>
          <Text color="gray">Enter new value (paste supported, press Enter to save, Escape to cancel):</Text>
        </Box>
        <Box borderStyle="single" padding={1}>
          <TextInput
            value={keyInput}
            onChange={setKeyInput}
            onSubmit={(value) => {
              const updatedKey = { ...editingKey, value };
              saveApiKey(updatedKey);
              setMode('apikeys');
              setEditingKey(null);
              setKeyInput('');
            }}
            placeholder="Paste or type your API key here..."
          />
        </Box>
      </Box>
    );
  }

  if (mode === 'editconfig' && editingConfig) {
    return (
      <Box flexDirection="column">
        <Box marginBottom={1}>
          <Text color="cyan" bold>Edit Configuration: {editingConfig.name}</Text>
        </Box>
        <Box marginBottom={1}>
          <Text color="gray">Press 'o' to open in editor, 'r' to reload, 'b' to go back</Text>
        </Box>
        <Box borderStyle="single" padding={1}>
          <Text>{configInput}</Text>
        </Box>
        <Box marginTop={1}>
          <Text color="yellow">💡 Use external editor to modify: {editingConfig.path}</Text>
        </Box>
        <Box marginTop={1}>
          <Text color="gray">
            To edit: Open the file in your preferred editor, make changes, then press 'r' to reload
          </Text>
        </Box>
      </Box>
    );
  }

  if (mode === 'select') {
    return (
      <Box flexDirection="column">
        <Box marginBottom={1}>
          <Text color="cyan" bold>Configuration Selector</Text>
        </Box>
        <Box marginBottom={1}>
          <Text color="gray">Use ↑/↓ to navigate, Enter to preview, 'b' to go back, 'q' to quit</Text>
        </Box>
        <Box flexDirection="column">
          {configs.map((config, index) => (
            <Box key={config.name}>
              <Text color={index === selectedIndex ? 'green' : 'white'}>
                {index === selectedIndex ? '► ' : '  '}
                {config.name}
              </Text>
            </Box>
          ))}
        </Box>
      </Box>
    );
  }

  return (
    <Box flexDirection="column">
      <Box marginBottom={1}>
        <Text color="yellow" bold>
{`
 ██████╗ ██████╗ ███████╗███╗   ██╗███╗   ███╗██╗███╗   ██╗██████╗ 
██╔═══██╗██╔══██╗██╔════╝████╗  ██║████╗ ████║██║████╗  ██║██╔══██╗
██║   ██║██████╔╝█████╗  ██╔██╗ ██║██╔████╔██║██║██╔██╗ ██║██║  ██║
██║   ██║██╔═══╝ ██╔══╝  ██║╚██╗██║██║╚██╔╝██║██║██║╚██╗██║██║  ██║
╚██████╔╝██║     ███████╗██║ ╚████║██║ ╚═╝ ██║██║██║ ╚████║██████╔╝
 ╚═════╝ ╚═╝     ╚══════╝╚═╝  ╚═══╝╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝╚═════╝ 
`}
        </Text>
      </Box>
      <Box marginBottom={1}>
        <Text color="cyan" bold>Main Menu</Text>
      </Box>
      <Box marginBottom={1}>
        <Text color="gray">Use ↑/↓ to navigate, Enter to select, 'q' to quit</Text>
      </Box>
      <Box flexDirection="column">
        <Box>
          <Text color={selectedIndex === 0 ? 'green' : 'white'}>
            {selectedIndex === 0 ? '► ' : '  '}
            Run Configurations
          </Text>
        </Box>
        <Box>
          <Text color={selectedIndex === 1 ? 'green' : 'white'}>
            {selectedIndex === 1 ? '► ' : '  '}
            Manage API Keys
          </Text>
        </Box>
      </Box>
    </Box>
  );
};

render(<App />); 