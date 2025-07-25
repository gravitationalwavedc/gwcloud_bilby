import { useContext } from 'react';
import { Container, Col, Card, Button, Row } from 'react-bootstrap';
import Link from 'found/Link';
import { UserContext } from '../sessionUser';

const NotFound = ({ match, router }) => {
    const user = useContext(UserContext);
    const isAuthenticated = user.isAuthenticated;

    return (
        <Container fluid>
            <Col md={{ offset: 2, span: 8 }} lg={{ offset: 3, span: 6 }} className="mb-5">
                <Card className="gw-form-card text-center">
                    <Card.Body className="py-5">
                        <div className="mb-4">
                            <h1 className="display-1 text-muted mb-0">404</h1>
                            <h2 className="h4 mb-3">Page Not Found</h2>
                            <p className="text-muted mb-4">
                                The page you&apos;re looking for doesn&apos;t exist or has been moved.
                            </p>
                        </div>

                        <Row className="justify-content-center">
                            <Col xs="auto">
                                <div className="text-center">
                                    <Link to="/" match={match} router={router} className="m-2">
                                        <Button variant="primary" size="lg">
                                            Public Jobs
                                        </Button>
                                    </Link>

                                    {isAuthenticated ? (
                                        <>
                                            <Link to="/job-list" match={match} router={router} className="m-2">
                                                <Button variant="outline-primary" size="lg">
                                                    My Jobs
                                                </Button>
                                            </Link>
                                            <Link to="/job-form" match={match} router={router} className="m-2">
                                                <Button variant="outline-primary" size="lg">
                                                    Create New Job
                                                </Button>
                                            </Link>
                                        </>
                                    ) : (
                                        <a href={`${import.meta.env.VITE_BACKEND_URL}/sso/login/`} className="m-2">
                                            <Button variant="outline-primary" size="lg">
                                                Login
                                            </Button>
                                        </a>
                                    )}
                                </div>
                            </Col>
                        </Row>

                        <div className="mt-4">
                            <small className="text-muted">Need help? Contact the GWCloud team for assistance.</small>
                        </div>
                    </Card.Body>
                </Card>
            </Col>
        </Container>
    );
};

export default NotFound;
