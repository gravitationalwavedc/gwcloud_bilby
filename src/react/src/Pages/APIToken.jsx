import { useState } from 'react';
import { Row, Col, Button, Container, Card, Form } from 'react-bootstrap';
import { graphql, createFragmentContainer, commitMutation } from 'react-relay';
import FormCard from '../Components/Forms/FormCard';
import { CopyButton, CheckButton } from '../Components/CustomButtons';
import moment from 'moment';
import Environment from '../environment.js';

const APIToken = ({ data }) => {
    const [tokens, setTokens] = useState(data.listApiTokens);
    const [isCreatingToken, setIsCreatingToken] = useState(false);
    const [tokenName, setTokenName] = useState('');
    const [tokenCreationError, setTokenCreationError] = useState('');
    const [newlyCreatedToken, setNewlyCreatedToken] = useState(null);

    function revoke(id) {
        commitMutation(Environment, {
            mutation: graphql`
                mutation APITokenRevokeMutation($id: ID!) {
                    deleteApiToken(id: $id) {
                        success
                    }
                }
            `,
            variables: { id },
            onCompleted: (response) => {
                if (response && response.deleteApiToken.success === true) {
                    setTokens(tokens.filter((e) => e.id !== id));
                }
            },
        });
    }
    function createToken(name) {
        setTokenCreationError('');
        commitMutation(Environment, {
            mutation: graphql`
                mutation APITokenCreateMutation($name: String) {
                    createApiToken(name: $name) {
                        id
                        token
                        expiry
                        shortcode
                    }
                }
            `,
            variables: { name },
            onCompleted: (response) => {
                if (response && response.createApiToken.token) {
                    const { createApiToken: newToken } = response;
                    setNewlyCreatedToken({
                        id: newToken.id,
                        token: newToken.token,
                        name: name,
                    });
                    setTokens([
                        {
                            id: newToken.id,
                            token: newToken.token,
                            lastUsed: Date.now(),
                            name: name,
                            expired: false,
                            expiry: newToken.expiry,
                            shortcode: newToken.shortcode,
                        },
                        ...tokens,
                    ]);
                    setIsCreatingToken(false);
                    setTokenName('');
                }
            },
            onError: () => {
                setTokenCreationError(
                    'An error occurred while creating the token - ensure you do not already have a token with the same name',
                );
            },
        });
    }

    const renderTokenActions = () => {
        if (newlyCreatedToken) {
            // Show the newly created token with copy button and warning
            return (
                <div className="mt-3">
                    <div className="alert alert-warning">
                        <strong>Warning:</strong> This is the only time this token will be visible.
                        <div className="align-items-center mt-2">
                            <h5>{newlyCreatedToken.name}</h5>
                            <code className="mr-4">{newlyCreatedToken.token}</code>
                            <CopyButton
                                variant="outline-secondary"
                                content="Copy"
                                copyContent={newlyCreatedToken.token}
                            />
                        </div>
                    </div>
                </div>
            );
        } else if (isCreatingToken) {
            // Show the token name input form
            return (
                <Form
                    onSubmit={(e) => {
                        e.preventDefault();
                        if (!tokenName.trim()) {
                            setTokenCreationError('Token name cannot be empty');
                            return;
                        }
                        createToken(tokenName);
                    }}
                    className="mt-3"
                >
                    <Form.Group>
                        <Form.Label>Token Name</Form.Label>
                        <Form.Control
                            type="text"
                            value={tokenName}
                            onChange={(e) => setTokenName(e.target.value)}
                            isInvalid={!!tokenCreationError}
                            placeholder="Enter a name for your token"
                            autoFocus
                            maxLength={64}
                            style={{ textAlign: 'left' }}
                        />
                        <Form.Control.Feedback type="invalid">{tokenCreationError}</Form.Control.Feedback>
                    </Form.Group>
                    <div className="d-flex ">
                        <Button variant="secondary" className="mr-2" onClick={() => setIsCreatingToken(false)}>
                            Cancel
                        </Button>
                        <Button variant="primary" type="submit">
                            Create
                        </Button>
                    </div>
                </Form>
            );
        } else {
            // Show the Create Token button
            return (
                <Button variant="primary" style={{ float: 'right' }} onClick={() => setIsCreatingToken(true)}>
                    Create Token
                </Button>
            );
        }
    };

    return (
        <Container className="pt-5" fluid>
            <Row className="mb-3">
                <Col md={{ span: 8, offset: 2 }}>
                    <h1>API Tokens</h1>
                    <p>
                        API tokens are used by{' '}
                        <a
                            href="https://gwcloud-python.readthedocs.io/en/latest/"
                            target="_blank"
                            rel="noopener noreferrer"
                        >
                            gwcloud-python
                        </a>{' '}
                        to authenticate you, allowing you to view proprietary data and submit new jobs.
                    </p>
                    {tokens.length ? (
                        <Row xs={1}>
                            {tokens.map((token) => (
                                <Col key={token.id} className="mb-2">
                                    <FormCard
                                        className={`${token.expired ? 'border-warning gw-form-card' : 'gw-form-card'}`}
                                    >
                                        <Card.Body
                                            className="d-flex align-items-center justify-content-between"
                                            style={{ padding: 0 }}
                                        >
                                            <div>
                                                <h5>{token.name}</h5>
                                                <p style={{ marginBottom: 0 }}>
                                                    <pre className="mb-0">{token.shortcode}...</pre>
                                                    Added on {moment(token.created).format('Do MMMM, YYYY')}
                                                    <br />
                                                    Last used {moment(token.lastUsed).fromNow()}
                                                    <br />
                                                    {token.expiry && token.expired ? (
                                                        <span className="text-warning">
                                                            Expired on {moment(token.expiry).format('Do MMMM, YYYY')}
                                                        </span>
                                                    ) : (
                                                        `Expires on ${moment(token.expiry).format('Do MMMM, YYYY')}`
                                                    )}
                                                </p>
                                            </div>
                                            <CheckButton
                                                variant="outline-danger"
                                                content="Revoke"
                                                cancelContent="Revoke Token?"
                                                onClick={() => revoke(token.id)}
                                            />
                                        </Card.Body>
                                    </FormCard>
                                </Col>
                            ))}
                        </Row>
                    ) : (
                        <p>You do not have any API tokens associated with your account.</p>
                    )}

                    {renderTokenActions()}
                </Col>
            </Row>
        </Container>
    );
};
export default createFragmentContainer(APIToken, {
    data: graphql`
        fragment APIToken_data on Query {
            listApiTokens {
                id
                name
                lastUsed
                created
                expiry
                expired
                shortcode
            }
        }
    `,
});
