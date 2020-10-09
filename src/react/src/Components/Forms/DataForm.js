import React from 'react';
import { Button, CardDeck, Col, Row, Form } from 'react-bootstrap';
import DetectorCard from './DetectorCard';
import FormCard from './FormCard';
import hanfordImg from '../../assets/hanford.png';
import virgoImg from '../../assets/Virgo.jpg';
import livingstonImg from '../../assets/livingston.png';

const DataForm = ({formik, handlePageChange}) =>
    <React.Fragment>
        <Row>
            <Col>
                <FormCard title="Data">
                    <Row className="mb-4">
                        <Col>
                            <Form.Label>Type of data</Form.Label>
                            <Form.Check 
                                custom 
                                id="typeOpen" 
                                label="Open" 
                                type="radio" 
                                name="dataChoice" 
                                value="open" 
                                onChange={formik.handleChange} 
                                checked={formik.values.dataChoice === 'open' ? true : false }/>
                            <Form.Check 
                                custom 
                                id="typeSimulated" 
                                label="Simulated" 
                                type="radio" 
                                name="dataChoice" 
                                value="simulated" 
                                onChange={formik.handleChange}
                                checked={formik.values.dataChoice === 'simulated' ? true : false }/>
                        </Col>
                        <Col>
                            <Form.Group controlId="triggerTime">
                                <Form.Label>Trigger time (GPS)</Form.Label>
                                <Form.Control 
                                    name="triggerTime" 
                                    type="number" 
                                    {...formik.getFieldProps('triggerTime')}/>
                            </Form.Group>
                        </Col>
                    </Row>
                    <Row>
                        <Col>
                            <Form.Group controlId="samplingFrequency">
                                <Form.Label>Sampling frequency</Form.Label>
                                <Form.Control 
                                    name="samplingFrequency" 
                                    as="select" 
                                    custom 
                                    {...formik.getFieldProps('samplingFrequency')}>
                                    <option>512 hz</option>
                                    <option>1024 hz</option>
                                    <option>2048 hz</option>
                                    <option>4096 hz</option>
                                    <option>8192 hz</option>
                                    <option>16384 hz</option>
                                </Form.Control>
                            </Form.Group>
                        </Col>
                        <Col>
                            <Form.Group controlId="signalDuration">
                                <Form.Label>Signal duration</Form.Label>
                                <Form.Control 
                                    name="signalDuration" 
                                    as="select" 
                                    custom 
                                    {...formik.getFieldProps('signalDuration')}>
                                    <option>4 seconds</option>
                                    <option>8 seconds</option>
                                    <option>16 seconds</option>
                                    <option>24 seconds</option>
                                    <option>32 seconds</option>
                                    <option>64 seconds</option>
                                    <option>128 seconds</option>
                                </Form.Control>
                            </Form.Group>
                        </Col>
                    </Row>
                </FormCard>
            </Col>
        </Row>
        <CardDeck>
            <DetectorCard title="Hanford" image={hanfordImg} formik={formik} />
            <DetectorCard title="Livingston" image={livingstonImg} formik={formik} />
            <DetectorCard title="Virgo" image={virgoImg} formik={formik}/>
        </CardDeck>
        <Row className="mt-4">
            <Col>
                <Button size="lg" onClick={() => handlePageChange('signal')}>Save and continue</Button>
            </Col>
        </Row>
    </React.Fragment>;


export default DataForm;
