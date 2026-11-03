import { Link } from 'react-router-dom';

export function Brand() {
  return <Link className="brand" to="/" aria-label="KONWUŚ — strona główna">
    <span className="brand-disc" aria-hidden="true"><span /></span>
    <span>KONWUŚ</span>
  </Link>;
}
