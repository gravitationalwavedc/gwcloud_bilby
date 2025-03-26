import React, { useState } from 'react';
import { Row, Nav, Col, Button, Container, Tab, Table } from 'react-bootstrap';
import { graphql, createFragmentContainer, commitMutation } from 'react-relay';
import FormCard from '../Components/Forms/FormCard'
import { CopyButton, CheckButton } from '../Components/CustomButtons'
import moment from 'moment';
import Environment from '../environment.js'

const APIToken = ({ data }) => {
  const [tokens, setTokens] = useState(data.listApiTokens.tokens);

  function revoke(uuid) {
    commitMutation(Environment, {
      mutation: graphql`mutation APITokenRevokeMutation($input: String!) {
        deleteApiToken(token:$input){
          success
        }
      }`,
      variables: { input: uuid },
      onCompleted: (response, errors) => {
        if (response && response.deleteApiToken.success === true) {
          setTokens(tokens.filter(e => e.token !== uuid))
        } else {
          console.error(errors);
        }

      }
    })
  }
  function createToken() {
    commitMutation(Environment, {
      mutation: graphql`mutation APITokenCreateMutation {
        createApiToken {
          token
        }
      }`,
      onCompleted: (response, errors) => {
        if (response && response.createApiToken.token) {
          setTokens([{
            token: response.createApiToken.token,
            lastUsed: Date.now(),
          }, ...tokens])
        } else {
          console.error(errors)
        }
      }
    });
  }

  return <Container className="pt-5" fluid>
    <Row className="mb-3">
      <Col md={{ span: 8, offset: 2 }}>
        <h1>API Tokens</h1>
        <p>API tokens are used by <a href="https://gwcloud-python.readthedocs.io/en/latest/" target="_blank" rel="noopener noreferrer">gwcloud-python</a> to authenticate you, allowing you to view proprietary data and submit new jobs.</p>
        <FormCard title="Tokens">{tokens.length
          ? <Table>
            <thead>
              <tr>
                <th>Token</th>
                <th>Last Used</th>
                <th>Revoke</th>
              </tr>
            </thead>
            <tbody>
              {tokens.map(e => <tr key={e.token}>
                <td className="align-items-center">{e.token} <CopyButton variant="text btn-link" content="Copy" copyContent={e.token} /></td>
                <td>{moment(e.lastUsed).format()} ({moment(e.lastUsed).fromNow()})</td>
                <td><CheckButton variant="text text-danger" content="Revoke" cancelContent="Revoke Token?" onClick={() => revoke(e.token)} /></td>
              </tr>)}
            </tbody>
          </Table>
          : <p>You do not have any API tokens associated with your account.</p>}

          <Button variant="primary" className="float-right" onClick={createToken}>Create Token</Button>
        </FormCard>
      </Col>
    </Row>
  </Container>
}
export default createFragmentContainer(APIToken, {
  data: graphql`
    fragment APIToken_data on Query {
      listApiTokens {
      tokens {
      token
              lastUsed
            }
          }
        }`,
});
