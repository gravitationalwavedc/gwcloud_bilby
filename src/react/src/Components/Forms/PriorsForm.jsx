import { Button, Col, Row, Form } from 'react-bootstrap';
import Input from './Atoms/Input';
import FormCard from './FormCard';

const PriorsForm = ({ formik, handlePageChange }) => (
    <Row>
        <Col>
            <FormCard title="Priors & Sampler">
                <Row>
                    <Col md={6}>
                        <Form.Group controlId="priorChoice">
                            <Form.Label>Priors</Form.Label>
                            <Form.Control
                                name="priorChoice"
                                as="select"
                                custom
                                value={formik.values.priorChoice}
                                {...formik.getFieldProps('priorChoice')}
                            >
                                <option>High Mass</option>
                                <option>4s</option>
                                <option>8s</option>
                                <option>16s</option>
                                <option>32s</option>
                                <option>64s</option>
                                <option>128s</option>
                                <option>128s tidal</option>
                            </Form.Control>
                        </Form.Group>
                    </Col>
                </Row>
                <Row>
                    <Col md={6}>
                        <Form.Group controlId="sampler">
                            <Form.Label>Sampler</Form.Label>
                            <Form.Control
                                name="sampler"
                                as="select"
                                aria-describedby="samplerHelp"
                                custom
                                {...formik.getFieldProps('sampler')}
                                disabled
                            >
                                <option>Dynesty</option>
                            </Form.Control>
                            <Form.Text id="samplerHelp" muted>
                                More samplers will be available soon.
                            </Form.Text>
                        </Form.Group>
                    </Col>
                </Row>
            </FormCard>
            <FormCard title="Sampler Parameters">
                <Row>
                    <Col>
                        <Input formik={formik} name="nlive" title="Live points" type="number" min="100" />
                    </Col>
                    <Col>
                        <Input formik={formik} name="nact" title="Auto-correlation steps" type="number" />
                    </Col>
                </Row>
                <Row>
                    <Col>
                        <Input formik={formik} name="maxmcmc" title="Maximum steps" type="number" />
                    </Col>
                    <Col>
                        <Input formik={formik} name="walks" title="Minimum walks" type="number" />
                    </Col>
                </Row>
                <Row>
                    <Col md={6}>
                        <Input formik={formik} name="dlogz" title="Stopping criteria" type="number" />
                    </Col>
                </Row>
            </FormCard>
            <Row>
                <Col>
                    <Button onClick={() => handlePageChange('review')}>Save and continue</Button>
                </Col>
            </Row>
        </Col>
    </Row>
);
export default PriorsForm;
