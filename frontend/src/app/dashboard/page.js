'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import Link from 'next/link';
import { useDropzone } from 'react-dropzone';
import { 
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell
} from 'recharts';
import { 
  LayoutDashboard, MessageSquare, UploadCloud, 
  Database, Activity, CheckCircle2, AlertCircle 
} from 'lucide-react';
import { fetchStats, fetchVectors, fetchTopics, uploadDocument } from '../../lib/api';
import './dashboard.css';

const TOPIC_COLORS = ['#6366f1', '#8b5cf6', '#d946ef', '#ec4899', '#3b82f6'];

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [vectors, setVectors] = useState([]);
  const [topics, setTopics] = useState([]);
  const [uploadStatus, setUploadStatus] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const isFetchingRef = useRef(false);

  const loadDashboardData = useCallback(async () => {
    if (isFetchingRef.current) return;
    isFetchingRef.current = true;

    try {
      const [statsData, vectorsData, topicsData] = await Promise.allSettled([
        fetchStats(),
        fetchVectors(),
        fetchTopics(),
      ]);

      if (statsData.status === 'fulfilled') setStats(statsData.value);
      if (vectorsData.status === 'fulfilled') setVectors(vectorsData.value.points || []);
      if (topicsData.status === 'fulfilled') setTopics(topicsData.value.clusters || []);
      setError(null);
    } catch (err) {
      setError('Failed to refresh dashboard metrics');
    } finally {
      setIsLoading(false);
      isFetchingRef.current = false;
    }
  }, []);

  useEffect(() => {
    loadDashboardData();
    const interval = setInterval(loadDashboardData, 12000);
    return () => clearInterval(interval);
  }, [loadDashboardData]);

  const onDrop = useCallback(async (acceptedFiles) => {
    const file = acceptedFiles[0];
    if (!file) return;

    if (file.size > 25 * 1024 * 1024) {
      setUploadStatus({ type: 'error', message: 'File size exceeds 25MB limit' });
      return;
    }

    setUploadStatus({ type: 'uploading', message: `Uploading ${file.name}...` });

    try {
      const result = await uploadDocument(file);
      setUploadStatus({
        type: 'success',
        message: `${result.original_name || file.name} uploaded successfully. Pending embedding.`,
      });
      loadDashboardData();
    } catch (err) {
      setUploadStatus({ type: 'error', message: err.message || 'Upload failed' });
    }

    setTimeout(() => setUploadStatus(null), 6000);
  }, [loadDashboardData]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({ 
    onDrop,
    accept: {
      'text/plain': ['.txt'],
      'application/pdf': ['.pdf'],
      'text/markdown': ['.md'],
      'application/json': ['.json'],
    },
    maxFiles: 1,
  });

  const CustomScatterTooltip = ({ active, payload }) => {
    if (active && payload && payload.length) {
      return (
        <div style={{
          background: 'rgba(15, 17, 23, 0.95)',
          border: '1px solid rgba(255,255,255,0.15)',
          padding: '10px 14px',
          borderRadius: '8px',
          maxWidth: '280px',
          color: '#e2e8f0',
          fontSize: '0.8rem',
          lineHeight: '1.4',
        }}>
          {payload[0].payload.content}
        </div>
      );
    }
    return null;
  };

  return (
    <div className="dashboard-container">
      <div className="dashboard-header">
        <div className="dashboard-header-left">
          <div className="header-icon" style={{ borderRadius: '12px', width: '42px', height: '42px', padding: '8px' }}>
            <LayoutDashboard size={26} />
          </div>
          <div>
            <h1>Data Analytics</h1>
            <p>System Performance & Vector Space Visualization</p>
          </div>
        </div>
        <Link href="/" className="nav-button">
          <MessageSquare size={18} /> Back to Chat
        </Link>
      </div>

      <div className="dashboard-content">
        {error && (
          <div style={{
            padding: '10px 16px',
            background: 'rgba(239, 68, 68, 0.1)',
            border: '1px solid rgba(239, 68, 68, 0.2)',
            color: '#ef4444',
            borderRadius: '8px',
            fontSize: '0.85rem',
          }}>
            {error}
          </div>
        )}

        {isLoading && !stats ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: '60px' }}>
            <Activity className="spinner" size={32} color="#6366f1" />
          </div>
        ) : (
          <>
            <div className="stats-grid">
              <div className="stat-card">
                <span className="stat-title">Total Documents</span>
                <span className="stat-value">{stats?.total_documents ?? 0}</span>
                <Database size={24} color="rgba(255,255,255,0.1)" style={{ position: 'absolute', right: 20, top: 20 }} />
              </div>
              <div className="stat-card">
                <span className="stat-title">Embedded Documents</span>
                <span className="stat-value">{stats?.embedded_documents ?? 0}</span>
                <CheckCircle2 size={24} color="rgba(255,255,255,0.1)" style={{ position: 'absolute', right: 20, top: 20 }} />
              </div>
              <div className="stat-card">
                <span className="stat-title">Chat Messages</span>
                <span className="stat-value">{stats?.total_messages ?? 0}</span>
                <MessageSquare size={24} color="rgba(255,255,255,0.1)" style={{ position: 'absolute', right: 20, top: 20 }} />
              </div>
              <div className="stat-card">
                <span className="stat-title">Avg Response Latency</span>
                <span className="stat-value">{stats?.avg_latency_seconds ?? 0}s</span>
                <Activity size={24} color="rgba(255,255,255,0.1)" style={{ position: 'absolute', right: 20, top: 20 }} />
              </div>
            </div>

            <div className="charts-grid">
              <div className="chart-card">
                <h3 className="chart-title">Document Vector Space (PCA 2D Projection)</h3>
                <div style={{ height: '350px', width: '100%', marginTop: '10px' }}>
                  {vectors.length > 0 ? (
                    <ResponsiveContainer width="100%" height="100%">
                      <ScatterChart margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
                        <XAxis type="number" dataKey="x" name="PCA 1" stroke="rgba(255,255,255,0.4)" tick={false} />
                        <YAxis type="number" dataKey="y" name="PCA 2" stroke="rgba(255,255,255,0.4)" tick={false} />
                        <Tooltip content={<CustomScatterTooltip />} cursor={{ strokeDasharray: '3 3' }} />
                        <Scatter name="Documents" data={vectors} fill="#8b5cf6" />
                      </ScatterChart>
                    </ResponsiveContainer>
                  ) : (
                    <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
                      No vector data indexed yet. Upload documents and run ingestion.
                    </div>
                  )}
                </div>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                <div className="chart-card">
                  <h3 className="chart-title">Ingest Document</h3>
                  <div 
                    {...getRootProps()} 
                    className={`dropzone-container ${isDragActive ? 'active' : ''}`}
                  >
                    <input {...getInputProps()} />
                    <UploadCloud className="dropzone-icon" />
                    {isDragActive ? (
                      <p>Drop file to upload...</p>
                    ) : (
                      <p style={{ fontSize: '0.88rem', color: 'var(--text-secondary)' }}>
                        Drag & drop a .txt, .pdf, .md, or .json file here
                      </p>
                    )}
                  </div>
                  
                  {uploadStatus && (
                    <div style={{ 
                      marginTop: '10px', 
                      padding: '10px 14px', 
                      borderRadius: '8px', 
                      display: 'flex', 
                      alignItems: 'center', 
                      gap: '8px',
                      fontSize: '0.85rem',
                      background: uploadStatus.type === 'success' ? 'rgba(34, 197, 94, 0.1)' : uploadStatus.type === 'error' ? 'rgba(239, 68, 68, 0.1)' : 'rgba(255,255,255,0.05)',
                      color: uploadStatus.type === 'success' ? '#22c55e' : uploadStatus.type === 'error' ? '#ef4444' : 'white',
                      border: `1px solid ${uploadStatus.type === 'success' ? 'rgba(34,197,94,0.2)' : uploadStatus.type === 'error' ? 'rgba(239,68,68,0.2)' : 'rgba(255,255,255,0.1)'}`,
                    }}>
                      {uploadStatus.type === 'success' && <CheckCircle2 size={16} />}
                      {uploadStatus.type === 'error' && <AlertCircle size={16} />}
                      {uploadStatus.type === 'uploading' && <Activity className="spinner" size={16} />}
                      {uploadStatus.message}
                    </div>
                  )}
                </div>

                <div className="chart-card" style={{ flex: 1 }}>
                  <h3 className="chart-title">Trending Query Topics</h3>
                  <div style={{ height: '200px', width: '100%', marginTop: '10px' }}>
                    {topics.length > 0 ? (
                      <ResponsiveContainer width="100%" height="100%">
                        <PieChart>
                          <Pie
                            data={topics}
                            cx="50%"
                            cy="50%"
                            innerRadius={45}
                            outerRadius={80}
                            paddingAngle={5}
                            dataKey="count"
                          >
                            {topics.map((entry, index) => (
                              <Cell key={`topic-cell-${index}`} fill={TOPIC_COLORS[index % TOPIC_COLORS.length]} />
                            ))}
                          </Pie>
                          <Tooltip 
                            contentStyle={{ background: 'rgba(15,17,23,0.95)', border: '1px solid #333', borderRadius: '8px' }}
                            itemStyle={{ color: 'white' }}
                          />
                        </PieChart>
                      </ResponsiveContainer>
                    ) : (
                      <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-secondary)', fontSize: '0.88rem' }}>
                        Insufficient chat queries to cluster topics (minimum 3 required).
                      </div>
                    )}
                  </div>
                </div>
              </div>

            </div>
          </>
        )}
      </div>
    </div>
  );
}
