import React from 'react';
import { Button, Col, Row, Form } from 'react-bootstrap';
import FormCard from './FormCard';

const PriorsForm = ({formik, handlePageChange}) =>
    <Row>
        <Col>
            <FormCard title="Priors & Sampler">
                <Row className="mb-4">
                    <Col md={6}>
                        <Form.Group controlId="priorsChoice">
                            <Form.Label>Priors</Form.Label>
                            <Form.Control 
                                name="priorsChoice" 
                                as="select" 
                                custom 
                                value={formik.values.priorsChoice}
                                {...formik.getFieldProps('priorsChoice')}>
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
                <Row className="mb-4">
                    <Col md={6}>
                        <Form.Group controlId="sampler">
                            <Form.Label>Sampler</Form.Label>
                            <Form.Control 
                                name="sampler" 
                                as="select" 
                                aria-describedby="samplerHelp"
                                custom 
                                {...formik.getFieldProps('sampler')} 
                                disabled>
                                <option>Dynesty</option>
                            </Form.Control>
                            <Form.Text id="samplerHelp" muted>More samplers will be available soon.</Form.Text>
                        </Form.Group>
                    </Col>
                </Row>
            </FormCard>
            <FormCard title="Sampler Parameters">
                <Row className="mb-4">
                    <Col>
                        <Form.Group controlId="nlive">
                            <Form.Label>Live points</Form.Label>
                            <Form.Control name="nlive" type="number" {...formik.getFieldProps('nlive')}/>
                        </Form.Group>
                    </Col>
                    <Col>
                        <Form.Group controlId="nact">
                            <Form.Label>Auto-correlation steps</Form.Label>
                            <Form.Control name="nact" type="number" {...formik.getFieldProps('nact')}/>
                        </Form.Group>
                    </Col>
                </Row>
                <Row className="mb-4">
                    <Col>
                        <Form.Group controlId="maxmcmc">
                            <Form.Label>Maximum steps</Form.Label>
                            <Form.Control name="maxmcmc" type="number" {...formik.getFieldProps('maxmcmc')}/>
                        </Form.Group>
                    </Col>
                    <Col>
                        <Form.Group controlId="walks">
                            <Form.Label>Minimum walks</Form.Label>
                            <Form.Control name="walks" type="number" {...formik.getFieldProps('walks')}/>
                        </Form.Group>
                    </Col>
                </Row>
                <Row className="mb-4">
                    <Col md={6}>
                        <Form.Group controlId="dlogz">
                            <Form.Label>Stopping criteria</Form.Label>
                            <Form.Control name="dlogz" type="number" {...formik.getFieldProps('dlogz')}/>
                        </Form.Group>
                    </Col>
                </Row>
            </FormCard>
            <Row className="mt-4">
                <Col>
                    <Button size="lg" onClick={() => handlePageChange('review')}>Save and continue</Button>
                </Col>
            </Row>
        </Col>
    </Row>
;

export default PriorsForm;
