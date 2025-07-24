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
                                The page you're looking for doesn't exist or has been moved.
                            </p>
                        </div>

                        <Row className="justify-content-center">
                            <Col xs="auto">
                                <div className="d-grid gap-2 d-md-block">
                                    <Link to="/" match={match} router={router}>
                                        <Button variant="primary" size="lg" className="me-md-2 mb-2 mb-md-0">
                                            Public Jobs
                                        </Button>
                                    </Link>

                                    {isAuthenticated ? (
                                        <>
                                            <Link to="/job-list" match={match} router={router}>
                                                <Button variant="outline-primary" size="lg" className="me-md-2 mb-2 mb-md-0">
                                                    My Jobs
                                                </Button>
                                            </Link>
                                            <Link to="/job-form" match={match} router={router}>
                                                <Button variant="outline-primary" size="lg" className="mb-2 mb-md-0">
                                                    Create New Job
                                                </Button>
                                            </Link>
                                        </>
                                    ) : (
                                        <a href={`${import.meta.env.VITE_BACKEND_URL}/sso/login/`}>
                                            <Button variant="outline-primary" size="lg" className="mb-2 mb-md-0">
                                                Login with LIGO.ORG
                                            </Button>
                                        </a>
                                    )}
                                </div>
                            </Col>
                        </Row>

                        <div className="mt-4">
                            <small className="text-muted">
                                Need help? Contact the GWCloud team for assistance.
                            </small>
                        </div>
                    </Card.Body>
                </Card>
            </Col>
        </Container>
    );
};

export default NotFound;
