import React from 'react';
import { Button, Col, Row, Form } from 'react-bootstrap';
import FormCard from './FormCard';

const SignalForm = ({formik, handlePageChange}) => 
    <React.Fragment>
        <Row>
            <Col>
                <FormCard title="Signal">
                    <Row>
                        <Col>
                            <Form.Label>Injection</Form.Label>
                            <Form.Check 
                                custom 
                                id="binaryBlackHole" 
                                label="Binary Black Hole" 
                                type="radio" 
                                name="signalChoice" 
                                value="binaryBlackHole" 
                                onChange={formik.handleChange}
                                checked={formik.values.signalChoice === 'binaryBlackHole' ? true : false}
                            />
                            <Form.Check 
                                custom 
                                id="binaryNeutronStar" 
                                label="Binary Neutron Star" 
                                type="radio" 
                                name="signalChoice" 
                                value="binaryNeutronStar" 
                                onChange={formik.handleChange}
                                checked={formik.values.signalChoice === 'binaryNeutronStar' ? true : false}
                            />
                        </Col>
                    </Row>
                </FormCard>
            </Col>
        </Row>
        <Row>
            <Col>
                <FormCard title="Injected Signal Parameters">
                    <Row>
                        <Col>
                            <Form.Group controlId="mass1">
                                <Form.Label>Mass 1 (M&#9737;)</Form.Label>
                                <Form.Control name="mass1" type="number" {...formik.getFieldProps('mass1')}/>
                            </Form.Group>
                        </Col>
                        <Col>
                            <Form.Group controlId="mass2">
                                <Form.Label>Mass 2 (M&#9737;)</Form.Label>
                                <Form.Control name="mass2" type="number" {...formik.getFieldProps('mass2')}/>
                            </Form.Group>
                        </Col>
                    </Row>
                    <Row>
                        <Col>
                            <Form.Group controlId="luminosityDistance">
                                <Form.Label>Luminosity distance (Mpc)</Form.Label>
                                <Form.Control 
                                    name="luminosityDistance" 
                                    type="number" 
                                    {...formik.getFieldProps('luminosityDistance')}/>
                            </Form.Group>
                        </Col>
                        <Col>
                            <Form.Group controlId="mergerTime">
                                <Form.Label>Merger time (GPS)</Form.Label>
                                <Form.Control name="mergerTime" type="number" {...formik.getFieldProps('mergerTime')}/>
                            </Form.Group>
                        </Col>
                    </Row>
                    <Row>
                        <Col>
                            <Form.Group controlId="psi">
                                <Form.Label>psi</Form.Label>
                                <Form.Control name="psi" type="number" {...formik.getFieldProps('psi')}/>
                            </Form.Group>
                        </Col>
                        <Col>
                            <Form.Group controlId="iota">
                                <Form.Label>iota</Form.Label>
                                <Form.Control name="iota" type="number" {...formik.getFieldProps('iota')}/>
                            </Form.Group>
                        </Col>
                    </Row>
                    <Row>
                        <Col>
                            <Form.Group controlId="phase">
                                <Form.Label>Phase</Form.Label>
                                <Form.Control name="phase" type="number" {...formik.getFieldProps('phase')}/>
                            </Form.Group>
                        </Col>
                        <Col />
                    </Row>
                    <Row>
                        <Col>
                            <Form.Group controlId="ra">
                                <Form.Label>Right ascension (radians)</Form.Label>
                                <Form.Control name="ra" type="number" {...formik.getFieldProps('ra')}/>
                            </Form.Group>
                        </Col>
                        <Col>
                            <Form.Group controlId="dec">
                                <Form.Label>Declination (degrees)</Form.Label>
                                <Form.Control name="dec" type="number" {...formik.getFieldProps('dec')}/>
                            </Form.Group>
                        </Col>
                    </Row>
                </FormCard>
            </Col>
        </Row>
        <Row className="mt-4">
            <Col>
                <Button size="lg" onClick={() => handlePageChange('priorsAndSampler')}>Save and continue</Button>
            </Col>
        </Row>
    </React.Fragment>;

export default SignalForm;
