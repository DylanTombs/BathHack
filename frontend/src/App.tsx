import { Layout } from './components/layout/Layout';
import { useWebSocket } from './hooks/useWebSocket';

// Mount WS connection at app root
function AppInner() {
  useWebSocket();
  return <Layout />;
}

function App() {
  return <AppInner />;
}

export default App;
