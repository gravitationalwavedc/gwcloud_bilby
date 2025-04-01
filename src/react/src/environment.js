
import { Environment, RecordSource, Store } from 'relay-runtime';
import { RelayNetworkLayer, urlMiddleware } from 'react-relay-network-modern';
import 'regenerator-runtime/runtime';

const network = new RelayNetworkLayer([urlMiddleware({
  url: () => `${import.meta.env.VITE_BACKEND_URL}/graphql`,
  credentials: 'same-origin',
}), (next) => async (req) => {
  req.fetchOpts.credentials = 'same-origin'; // allow to send cookies (sending credentials to same domains)

  req.fetchOpts.credentials = 'include'; // allow to send cookies for CORS (sending credentials to other domains)

  const res = await next(req);

  return res;
},])

const source = new RecordSource();
const store = new Store(source);
const environment = new Environment({ network, store });

export default environment;
