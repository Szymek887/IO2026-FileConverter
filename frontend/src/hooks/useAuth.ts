import { useContext } from 'react';
import { AuthContext } from '../auth/AuthProvider';

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth musi być użyty wewnątrz AuthProvider.');
  return context;
}
