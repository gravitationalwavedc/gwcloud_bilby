
import { Environment, RecordSource, Store } from 'relay-runtime';
import { RelayNetworkLayer, urlMiddleware } from 'react-relay-network-modern';
import 'regenerator-runtime/runtime';

const network = new RelayNetworkLayer([urlMiddleware({
  url: () => 'http://localhost:8001/graphql',
  credentials: 'same-origin',
}), (next) => async (req) => {
  // req.fetchOpts.method = 'GET'; // change default POST request method to GET
  // req.fetchOpts.headers['X-Request-ID'] = uuid.v4(); // add `X-Request-ID` to request headers
  req.fetchOpts.credentials = 'same-origin'; // allow to send cookies (sending credentials to same domains)
  // req.fetchOpts.credentials = 'include'; // allow to send cookies for CORS (sending credentials to other domains)

  console.log('RelayRequest', req);

  const res = await next(req);
  console.log('RelayResponse', res);

  return res;
},])

const source = new RecordSource();
const store = new Store(source);
const environment = new Environment({ network, store });

console.log(environment);
export default environment;
